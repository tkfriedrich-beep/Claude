"""Regression tests for the round-2 adversarial-review findings
(docs/reviews/codex-findings-r2.md). Each test fails on the pre-fix code and passes after.
Findings F1–F12.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cockpit.connectors.base import ConnectorError, ExecutionContext
from cockpit.connectors.local_files import LocalFilesConnector
from cockpit.connectors.mcp import MCPConnector
from cockpit.connectors.n8n import N8nConnector
from cockpit.connectors.obsidian import ObsidianConnector
from cockpit.enums import (
    Autonomy,
    ConnectorMode,
    EventType,
    ExecMode,
    PolicyKind,
    RiskLevel,
    RunStatus,
    ToolAccess,
    ToolCallStatus,
)
from cockpit.events import EventBus, get_bus
from cockpit.ids import correlation_id, new_id
from cockpit.models import Approval, Connector, Run, RunEvent, ToolCall, Workspace
from cockpit.policy import Outcome, PolicyContext, Rule, ToolSpec, evaluate
from cockpit.registry import get_registry

REPO_ROOT = Path(__file__).resolve().parents[3]
CONNECTORS = REPO_ROOT / "connectors"


# --------------------------------------------------------------------------- helpers
def _pol_ctx(**kw) -> PolicyContext:
    defaults = dict(
        safe_mode=False,
        kill_switch=False,
        exec_mode=ExecMode.ACT,
        shadow=False,
        autonomy=Autonomy.ACT_WITH_APPROVAL,
        skill_slug="s",
        skill_allowlist=frozenset(),
        domain_enabled=True,
        connector_enabled=True,
        connector_mode=ConnectorMode.READ_WRITE,
        rules=(),
    )
    defaults.update(kw)
    return PolicyContext(**defaults)


def _ctx(roots=None, *, dry_run=False, config=None) -> ExecutionContext:
    return ExecutionContext(
        workspace_id="w",
        run_id="run1",
        correlation_id="c",
        dry_run=dry_run,
        roots=roots or [],
        config=config or {},
    )


async def _mkrun(workspace_id: str, **kw) -> Run:
    from cockpit.db import db_session

    async with db_session() as session:
        run = Run(
            id=new_id("run"),
            workspace_id=workspace_id,
            status=kw.pop("status", "executing"),
            mode=kw.pop("mode", "act"),
            correlation_id=correlation_id(),
            **kw,
        )
        session.add(run)
        await session.commit()
        return run


# --------------------------------------------------------------------------- F1
def test_f1_safe_mode_beats_allow_rule_for_untrusted_external_read() -> None:
    """An ALLOW rule must NOT let a user-registered connector's external read fire in Safe Mode."""
    tool = ToolSpec(
        tool_id="n8n.report",
        connector_slug="n8n",
        access=ToolAccess.READ,
        risk_level=RiskLevel.R1,
        external_side_effects=True,
        supports_dry_run=False,
        idempotent=False,
        trusted=False,
    )
    allow = Rule(kind=PolicyKind.ALLOW, tool_id="n8n.report")

    denied = evaluate(tool, _pol_ctx(safe_mode=True, rules=(allow,)))
    assert denied.outcome is Outcome.DENY
    assert "safe mode" in denied.reason.lower()

    # sanity: with Safe Mode off, the same allow rule DOES permit it (proves the rule is real)
    allowed = evaluate(tool, _pol_ctx(safe_mode=False, rules=(allow,)))
    assert allowed.outcome is Outcome.ALLOW


# --------------------------------------------------------------------------- F2
async def test_f2_n8n_preview_makes_no_http_call() -> None:
    """preview() is a LOCAL description — it must never reach out to the webhook URL."""
    connector = N8nConnector(CONNECTORS)
    # URL points at a closed port: any real HTTP attempt would raise/hang.
    connector.runtime_config = {
        "webhooks": [
            {"name": "deploy", "url": "http://127.0.0.1:1/never", "supports_dry_run": True}
        ]
    }
    result = await asyncio.wait_for(
        connector.preview("n8n.deploy", {"env": "prod"}, _ctx(dry_run=True)), timeout=3
    )
    assert result.ok
    assert result.data.get("preview") is True
    assert "Would POST" in result.data["diff"] and "prod" in result.data["diff"]


# --------------------------------------------------------------------------- F3
def test_f3_write_to_hardlinked_file_is_rejected(workspace: dict, tmp_path: Path) -> None:
    """A hardlink inside a root shares an inode with an outside file — writing it is refused."""
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("original")
    link = root / "hard.md"
    os.link(outside, link)  # same inode as `outside`, st_nlink == 2

    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    with pytest.raises(ConnectorError, match="hardlink"):
        connector._write({"path": str(link), "content": "pwned"}, _ctx([root]))
    assert outside.read_text() == "original"  # untouched


# --------------------------------------------------------------------------- F4
def test_f4_list_rejects_dotdot_glob(workspace: dict, tmp_path: Path) -> None:
    """A `../*` glob must be refused before it can enumerate a parent directory."""
    root = tmp_path / "vault"
    root.mkdir()
    (tmp_path / "secret.md").write_text("secret")
    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    with pytest.raises(ConnectorError, match="glob"):
        connector._list({"root": str(root), "glob": "../*"}, _ctx([root]))


def test_f4_symlinked_entry_inside_root_is_not_listed(workspace: dict, tmp_path: Path) -> None:
    """A symlink planted in a root that points outside must not surface in listings."""
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("secret")
    (root / "real.md").write_text("hi")
    (root / "leak.md").symlink_to(outside)  # symlinked entry escaping the root

    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    result = connector._list({"root": str(root), "glob": "*"}, _ctx([root]))
    names = {e["rel_path"] for e in result.data["entries"]}
    assert "real.md" in names
    assert "leak.md" not in names  # symlink skipped (review R2-F4)


# --------------------------------------------------------------------------- F5 (see R3-F10)
async def _make_pending_approval(ws_id: str) -> tuple[str, str]:
    from cockpit.db import db_session

    run = await _mkrun(ws_id, kind="chat")
    async with db_session() as session:
        tc = ToolCall(
            id=new_id("tc"),
            workspace_id=ws_id,
            run_id=run.id,
            tool_id="local_files.write",
            connector_slug="local-files",
            status=ToolCallStatus.PROPOSED.value,
            risk_level="R2",
            idempotency_key=new_id("k"),
        )
        session.add(tc)
        apr = Approval(
            id=new_id("apr"),
            workspace_id=ws_id,
            run_id=run.id,
            tool_call_id=tc.id,
            status="pending",
            title="Write",
            confirm_phrase_required=False,
        )
        session.add(apr)
        await session.commit()
        return tc.id, apr.id


async def test_f5_edited_input_secret_rejected_normal_stored_raw(workspace: dict) -> None:
    """Secret-shaped edited input is rejected (R2-F5); normal edits are stored RAW so the resume
    executes the real value, not a redacted mask (R3-F10)."""
    from fastapi import HTTPException

    from cockpit.api.approvals import resolve_approval
    from cockpit.db import db_session
    from cockpit.schemas import ApprovalResolveRequest

    ws_id = workspace["workspace_id"]

    # 1) a raw credential in edited input is refused, never masked-and-executed
    _, apr_id = await _make_pending_approval(ws_id)
    async with db_session() as session:
        ws = await session.get(Workspace, ws_id)
        with pytest.raises(HTTPException) as exc:
            await resolve_approval(
                apr_id,
                ApprovalResolveRequest(
                    decision="approve",
                    edited_input={"content": "Bearer ABCDEFGHIJKLMNOPQRSTUV", "path": "x.md"},
                ),
                ws,
                session,
            )
        assert exc.value.status_code == 422

    # 2) a normal edit is stored verbatim (the executable source of truth)
    tc_id, apr_id = await _make_pending_approval(ws_id)
    async with db_session() as session:
        ws = await session.get(Workspace, ws_id)
        await resolve_approval(
            apr_id,
            ApprovalResolveRequest(
                decision="approve", edited_input={"content": "hello world", "path": "notes/x.md"}
            ),
            ws,
            session,
        )
    async with db_session() as session:
        tc = await session.get(ToolCall, tc_id)
        assert tc.edited_input == {
            "content": "hello world",
            "path": "notes/x.md",
        }  # raw, not masked


# --------------------------------------------------------------------------- F6
async def test_f6_n8n_idempotency_key_covers_the_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two different inputs to one webhook in one run must get different idempotency keys."""
    connector = N8nConnector(CONNECTORS)
    connector.runtime_config = {"webhooks": [{"name": "wf", "url": "http://x/hook"}]}
    seen: list[str] = []

    class FakeResp:
        status_code = 200
        text = "{}"

        def json(self) -> dict:
            return {"ok": True}

    async def fake_post(self, url, content=None, headers=None):
        seen.append(headers["X-Cockpit-Idempotency-Key"])
        return FakeResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    ctx = _ctx(dry_run=False)
    await connector.execute("n8n.wf", {"a": 1}, ctx)
    await connector.execute("n8n.wf", {"a": 2}, ctx)
    await connector.execute("n8n.wf", {"a": 1}, ctx)

    assert seen[0] != seen[1]  # different input → different key (no silent collision)
    assert seen[0] == seen[2]  # same input+run → stable key (real idempotency)


# --------------------------------------------------------------------------- F7
def test_f7_obsidian_write_rejects_dotdot_and_absolute(workspace: dict, tmp_path: Path) -> None:
    """An Obsidian note path with `..`/absolute must not escape the vault into another root."""
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    connector = ObsidianConnector(CONNECTORS)
    # ideas + vault are both roots; the escape would otherwise land in ideas/
    ctx = _ctx([vault, tmp_path / "ideas"])

    with pytest.raises(ConnectorError, match="relative to the vault"):
        connector._delegate_write(
            vault, {"path": "../ideas/evil.md", "content": "x"}, ctx, preview=False
        )
    with pytest.raises(ConnectorError, match="relative to the vault"):
        connector._delegate_write(
            vault, {"path": str(tmp_path / "abs.md"), "content": "x"}, ctx, preview=False
        )
    # a legitimate relative path still writes
    ok = connector._delegate_write(
        vault, {"path": "raw/ok.md", "content": "hi"}, ctx, preview=False
    )
    assert ok.ok and (vault / "raw" / "ok.md").read_text() == "hi"


# --------------------------------------------------------------------------- F8
def test_f8_n8n_prefers_ctx_config_over_singleton() -> None:
    """Execution reads THIS workspace's webhook config, not whatever last refreshed the global."""
    connector = N8nConnector(CONNECTORS)
    connector.runtime_config = {"webhooks": [{"name": "A", "url": "http://a/"}]}  # workspace A
    ctx_b = _ctx(config={"webhooks": [{"name": "B", "url": "http://b/"}]})  # workspace B

    assert [h["name"] for h in connector._webhooks(ctx_b)] == ["B"]  # routes to B
    assert [h["name"] for h in connector._webhooks()] == ["A"]  # fallback = singleton


def test_f8_mcp_prefers_ctx_config_over_singleton() -> None:
    connector = MCPConnector(CONNECTORS)
    connector.runtime_config = {"servers": [{"name": "A", "transport": "inproc"}]}
    ctx_b = _ctx(config={"servers": [{"name": "B", "transport": "inproc"}]})
    assert [s["name"] for s in connector._servers(ctx_b)] == ["B"]
    assert [s["name"] for s in connector._servers()] == ["A"]


# --------------------------------------------------------------------------- F9
async def test_f9_chat_denial_creates_no_ghost_events(workspace: dict) -> None:
    """A denied approval-gated chat tool leaves NO ToolCall/Approval/RunEvent rows behind."""
    from cockpit.db import db_session
    from cockpit.worker import RunProcessor
    from cockpit.workspace import update_workspace_settings

    ws_id = workspace["workspace_id"]
    processor = RunProcessor(workspace["settings"], get_registry(), get_bus())

    async with db_session() as session:
        await update_workspace_settings(session, ws_id, {"safe_mode": False})
        row = await session.scalar(
            select(Connector).where(
                Connector.workspace_id == ws_id, Connector.slug == "google-workspace"
            )
        )
        row.mode = "read_write"  # so create_event reaches REQUIRE_APPROVAL, not read-only deny
        await session.commit()

    run = await _mkrun(ws_id, status="executing", kind="chat")
    async with db_session() as session:
        run = await session.merge(run)
        allowed, _reason, _ = await processor._chat_permission(
            session,
            run,
            "google.calendar.create_event",
            {"title": "x", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z"},
        )
        await session.commit()
    assert allowed is False

    async with db_session() as session:
        tool_calls = (
            await session.scalars(select(ToolCall).where(ToolCall.run_id == run.id))
        ).all()
        approvals = (await session.scalars(select(Approval).where(Approval.run_id == run.id))).all()
        events = (await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all()
    assert tool_calls == []  # preflight decided read-only — nothing persisted
    assert approvals == []
    assert events == []  # no ghost SSE events to roll back (review R2-F9)


# --------------------------------------------------------------------------- F10
async def test_f10_persist_result_is_idempotent_across_replay(workspace: dict) -> None:
    """Re-running persistence (crash/resume) replaces this run's rows instead of duplicating."""
    from cockpit.db import db_session
    from cockpit.models import Artifact, Memory
    from cockpit.skills.base import ArtifactSpec, MemoryProposal, SkillResult
    from cockpit.worker import RunProcessor

    ws_id = workspace["workspace_id"]
    processor = RunProcessor(workspace["settings"], get_registry(), get_bus())
    run = await _mkrun(ws_id, status="executing", kind="skill", skill_slug="project-pulse")

    result = SkillResult(
        summary_md="done",
        artifacts=[ArtifactSpec(kind="markdown", title="Report", filename="r.md", content="# hi")],
        memory_proposals=[MemoryProposal(kind="working", content="remember this", rationale="x")],
    )

    async with db_session() as session:
        r = await session.merge(run)
        await processor._persist_result(session, r, result)
    async with db_session() as session:
        r = await session.merge(run)
        await processor._persist_result(session, r, result)  # replay after a simulated crash

    async with db_session() as session:
        artifacts = (await session.scalars(select(Artifact).where(Artifact.run_id == run.id))).all()
        memories = (await session.scalars(select(Memory).where(Memory.run_id == run.id))).all()
    assert len(artifacts) == 1  # not 2 — replaced, not duplicated
    assert len(memories) == 1


# --------------------------------------------------------------------------- F11
def test_f11_claim_ownership_predicate() -> None:
    """A queued run claimed by another worker is skipped; ones we own or already advanced run."""
    from types import SimpleNamespace

    from cockpit.worker import claim_still_owned

    me = "wrk-me"

    def run(status: str, claim: str | None) -> SimpleNamespace:
        return SimpleNamespace(status=status, worker_claim=claim)

    # R3-F13 tightened this to EXACT ownership (worker_claim == worker_id) regardless of status:
    # a cleared (None) or foreign claim must abort, not proceed.
    assert claim_still_owned(None, me) is False  # vanished
    assert claim_still_owned(run(RunStatus.QUEUED.value, "wrk-other"), me) is False  # stolen
    assert claim_still_owned(run(RunStatus.QUEUED.value, me), me) is True  # ours
    assert claim_still_owned(run(RunStatus.QUEUED.value, None), me) is False  # cleared → abort
    assert claim_still_owned(run(RunStatus.EXECUTING.value, "wrk-other"), me) is False  # foreign
    assert claim_still_owned(run(RunStatus.EXECUTING.value, me), me) is True  # still ours


# --------------------------------------------------------------------------- F12
async def test_f12_duplicate_run_seq_is_rejected_by_db(workspace: dict) -> None:
    """The DB enforces one sequence number per run — the backstop behind emit()'s retry."""
    from cockpit.db import db_session

    ws_id = workspace["workspace_id"]
    run = await _mkrun(ws_id, status="executing")
    async with db_session() as session:
        session.add(RunEvent(workspace_id=ws_id, run_id=run.id, seq=1, type="a"))
        session.add(RunEvent(workspace_id=ws_id, run_id=run.id, seq=1, type="b"))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_f12_emit_assigns_unique_sequential_seqs(workspace: dict) -> None:
    """emit() hands out monotonic, gap-free, unique per-run seqs under the lock."""
    from cockpit.db import db_session

    bus = EventBus()
    ws_id = workspace["workspace_id"]
    run = await _mkrun(ws_id, status="executing")
    async with db_session() as session:
        r = await session.merge(run)
        for _ in range(5):
            await bus.emit(
                session,
                workspace_id=ws_id,
                run_id=r.id,
                type=EventType.TOOL_PROGRESS,
                payload={"message": "x"},
            )
        seqs = (
            await session.scalars(
                select(RunEvent.seq).where(RunEvent.run_id == r.id).order_by(RunEvent.seq)
            )
        ).all()
        total = await session.scalar(
            select(func.count()).select_from(RunEvent).where(RunEvent.run_id == r.id)
        )
    assert list(seqs) == [1, 2, 3, 4, 5]
    assert total == 5
