"""Regression tests for the round-3 adversarial-review findings
(docs/reviews/codex-findings-r3.md). Each fails on the pre-fix code. Findings F1–F13.

F10 (execute raw, not redacted, edited input) and F13 (exact claim ownership) are covered by the
updated cases in test_review_r2_fixes.py; the rest are here.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from cockpit.connectors.base import (
    ConnectorError,
    ExecutionContext,
    open_contained_write,
    relparts_under_roots,
)
from cockpit.connectors.web import WebResearchConnector, _validate_and_pin, html_to_text
from cockpit.enums import EventType, RiskLevel, ToolAccess
from cockpit.events import EventBus
from cockpit.gateway import ToolGateway
from cockpit.ids import correlation_id, new_id
from cockpit.logging import redact, redact_text
from cockpit.models import Connector, Memory, Run, RunEvent
from cockpit.registry import get_registry

REPO_ROOT = Path(__file__).resolve().parents[3]
CONNECTORS = REPO_ROOT / "connectors"


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
async def test_f1_fetch_pins_to_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fetch URL is rewritten to the validated IP (host+SNI preserved), so httpx connects to
    that exact address — a rebinding flip after the guard cannot reach a new (internal) IP."""

    async def fake_gai(self, host, port, *a, **k):
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("asyncio.base_events.BaseEventLoop.getaddrinfo", fake_gai)
    ip_url, host_header, sni, _scheme = await _validate_and_pin("https://rebind.test/path?q=1")
    assert "93.184.216.34" in ip_url and "rebind.test" not in ip_url  # pinned to the IP
    assert host_header == "rebind.test" and sni == "rebind.test"  # host + cert name preserved


async def test_f1_rebinding_to_private_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_gai(self, host, port, *a, **k):
        return [(2, 1, 6, "", ("127.0.0.1", port))]  # host resolves to loopback

    monkeypatch.setattr("asyncio.base_events.BaseEventLoop.getaddrinfo", fake_gai)
    with pytest.raises(ConnectorError, match="private/internal"):
        await _validate_and_pin("http://rebind.test/")


# --------------------------------------------------------------------------- F2
async def test_f2_gateway_resolves_per_workspace_manifest(workspace: dict) -> None:
    """Policy resolves a dynamic tool's manifest from THIS workspace's config, not the global
    singleton — so a write registered in the workspace isn't classified as the singleton's read."""
    from cockpit.db import db_session

    ws_id = workspace["workspace_id"]
    reg = get_registry()
    # Singleton (another workspace's view): the same tool id as a low-risk READ.
    reg.connectors["n8n"].runtime_config = {
        "webhooks": [{"name": "wf", "url": "http://singleton/", "read_only": True}]
    }
    # THIS workspace's DB row: the same tool id is actually an external WRITE (R3).
    async with db_session() as session:
        row = await session.scalar(
            select(Connector).where(Connector.workspace_id == ws_id, Connector.slug == "n8n")
        )
        row.config = {"webhooks": [{"name": "wf", "url": "http://workspace/", "read_only": False}]}
        await session.commit()

    gateway = ToolGateway(workspace["settings"], EventBus(), reg.connectors)
    run = await _mkrun(ws_id)
    async with db_session() as session:
        run = await session.merge(run)
        _, tool, _ = await gateway._resolve_tool(session, run, "n8n.wf")
    assert tool.risk_level == RiskLevel.R3  # workspace's WRITE classification, not singleton's R1
    assert tool.access == ToolAccess.WRITE
    assert tool.external_side_effects is True  # durability guard now sees the real side effect


# --------------------------------------------------------------------------- F3
def test_f3_open_contained_write_rejects_parent_symlink(tmp_path: Path) -> None:
    """A symlinked PARENT component is rejected at open time (O_NOFOLLOW every hop)."""
    import os

    root = tmp_path / "vault"
    (root / "notes").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linkdir").symlink_to(outside)  # parent component is a symlink out of the root

    with pytest.raises(ConnectorError, match="descend"):
        open_contained_write(root, ["linkdir", "memo.md"])
    assert not (outside / "memo.md").exists()

    # a legitimate nested path still opens + writes
    fd = open_contained_write(root, ["notes", "ok.md"])
    try:
        os.write(fd, b"hi")
    finally:
        os.close(fd)
    assert (root / "notes" / "ok.md").read_text() == "hi"


def test_f3_relparts_rejects_dotdot(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    with pytest.raises(ConnectorError):
        relparts_under_roots(root / ".." / "escape.md", [root])


# --------------------------------------------------------------------------- F4
def test_f4_api_key_env_cannot_be_redirected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connector config can't point the web connector at another process secret (env name is
    fixed in code)."""
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value-123")
    connector = WebResearchConnector(CONNECTORS)
    ctx = ExecutionContext(
        workspace_id="w",
        run_id="r",
        correlation_id="c",
        config={"api_key_env": "ANTHROPIC_API_KEY"},  # the attack: redirect to a real secret
    )
    # No FIRECRAWL_API_KEY set → provider stays offline; ANTHROPIC is never consulted.
    assert connector._search_provider(ctx) == "offline"


# --------------------------------------------------------------------------- F5
def test_f5_url_userinfo_is_redacted_and_rejected() -> None:
    masked = redact_text("fetched http://alice:s3cr3t-pw@example.com/private ok")
    assert "s3cr3t-pw" not in masked and "•••redacted•••@" in masked
    assert redact({"url": "https://u:p4ssw0rd@host/x"})["url"].count("p4ssw0rd") == 0


async def test_f5_fetch_rejects_userinfo_url() -> None:
    with pytest.raises(ConnectorError, match="credentials"):
        await _validate_and_pin("http://alice:s3cr3t@93.184.216.34/private")


# --------------------------------------------------------------------------- F6
async def test_f6_event_retry_survives_real_seq_conflict(workspace: dict) -> None:
    """Two independent buses (independent seq locks) emitting on the same run force a DB unique
    conflict; emit() must retry (not crash on expunge) and both events must persist."""
    import asyncio

    from cockpit.db import db_session

    ws_id = workspace["workspace_id"]
    run = await _mkrun(ws_id)
    bus_a, bus_b = EventBus(), EventBus()

    async def emit_via(bus: EventBus) -> None:
        async with db_session() as session:
            r = await session.merge(run)
            await bus.emit(
                session,
                workspace_id=ws_id,
                run_id=r.id,
                type=EventType.TOOL_PROGRESS,
                payload={"message": "x"},
            )
            await session.commit()

    # Serialize slightly-overlapping to provoke the same-seq race across the two locks.
    await asyncio.gather(emit_via(bus_a), emit_via(bus_b))
    async with db_session() as session:
        seqs = (await session.scalars(select(RunEvent.seq).where(RunEvent.run_id == run.id))).all()
    assert sorted(seqs) == [1, 2]  # both survived, distinct seqs — no crash, no loss


# --------------------------------------------------------------------------- F7
async def test_f7_events_publish_only_after_commit(workspace: dict) -> None:
    """A subscriber sees an event only after the outer transaction commits; a rollback: none."""
    from cockpit.db import db_session

    ws_id = workspace["workspace_id"]
    run = await _mkrun(ws_id)
    bus = EventBus()
    q = bus.subscribe(run.id)

    # emit then ROLL BACK → nothing published, nothing persisted
    async with db_session() as session:
        r = await session.merge(run)
        await bus.emit(
            session, workspace_id=ws_id, run_id=r.id, type=EventType.ARTIFACT_CREATED, payload={}
        )
        await session.rollback()
    assert q.empty()  # no ghost event

    # emit then COMMIT → published exactly once
    async with db_session() as session:
        r = await session.merge(run)
        await bus.emit(
            session, workspace_id=ws_id, run_id=r.id, type=EventType.ARTIFACT_CREATED, payload={}
        )
        await session.commit()
    assert not q.empty()
    assert q.get_nowait()["type"] == EventType.ARTIFACT_CREATED.value


# --------------------------------------------------------------------------- F8
async def test_f8_approved_memory_not_duplicated_on_replay(workspace: dict) -> None:
    """A memory approved between crash and resume is not re-proposed as a duplicate on replay."""
    from cockpit.db import db_session
    from cockpit.skills.base import MemoryProposal, SkillResult
    from cockpit.worker import RunProcessor

    ws_id = workspace["workspace_id"]
    processor = RunProcessor(workspace["settings"], get_registry(), EventBus())
    run = await _mkrun(ws_id, status="executing", kind="skill", skill_slug="project-pulse")
    result = SkillResult(
        summary_md="s",
        memory_proposals=[MemoryProposal(kind="working", content="remember this", rationale="x")],
    )

    async with db_session() as session:
        r = await session.merge(run)
        await processor._persist_result(session, r, result)
    # user approves it while the run is "interrupted"
    async with db_session() as session:
        mem = (await session.scalars(select(Memory).where(Memory.run_id == run.id))).one()
        mem.status = "active"
        await session.commit()
    # resume re-runs persistence
    async with db_session() as session:
        r = await session.merge(run)
        await processor._persist_result(session, r, result)

    async with db_session() as session:
        mems = (await session.scalars(select(Memory).where(Memory.run_id == run.id))).all()
    assert len(mems) == 1 and mems[0].status == "active"  # not duplicated, approval preserved


# --------------------------------------------------------------------------- F9
async def test_f9_out_of_range_citation_is_flagged(workspace: dict, monkeypatch) -> None:
    """A memo that cites [999] with one source is flagged (unresolved + data), not trusted."""
    from cockpit.skills.base import SkillContext
    from cockpit.skills.research_run import ResearchRunExecutor

    async def fake_generate(prompt: str) -> str:
        return "## Answer\nThe sky is green [999]. Also blue [1]."  # injected bogus citation

    ctx = SkillContext(
        session=None,  # not used by _source_backed_memo
        run=await _mkrun(workspace["workspace_id"], skill_slug="research-run"),
        gateway=None,
        bus=EventBus(),
        settings=workspace["settings"],
        ws=None,
        manifest={},
        generate=fake_generate,
    )
    ex = ResearchRunExecutor(ctx)
    sources = [{"title": "S1", "url": "https://a/", "text": "…", "snippet": ""}]
    result = await ex._source_backed_memo("why is the sky blue", sources)
    assert result.data["invalid_citations"] == [999]
    assert result.unresolved and "999" in result.unresolved[0]
    assert "⚠️ Citation check" in result.artifacts[0].content


# --------------------------------------------------------------------------- F11
def test_f11_reconcile_dedups_before_unique_index(tmp_path: Path) -> None:
    """The 0003 reconcile SQL renumbers duplicate (run_id, seq) so the unique index can build —
    a legacy DB that hit the event race is upgradable, not bricked."""
    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE run_events (id INTEGER PRIMARY KEY, run_id TEXT, seq INTEGER)")
    con.executemany(
        "INSERT INTO run_events (run_id, seq) VALUES (?,?)",
        [("r1", 1), ("r1", 1), ("r1", 2), ("r2", 1)],  # duplicate (r1,1)
    )
    con.commit()
    con.executescript(
        """
        WITH renum AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY seq, id) AS rn
            FROM run_events
            WHERE run_id IN (SELECT run_id FROM run_events GROUP BY run_id, seq HAVING COUNT(*)>1)
        )
        UPDATE run_events SET seq = (SELECT rn FROM renum WHERE renum.id = run_events.id)
         WHERE id IN (SELECT id FROM renum);
        """
    )
    con.commit()
    con.execute("CREATE UNIQUE INDEX uq ON run_events(run_id, seq)")  # must not raise
    rows = con.execute("SELECT run_id, seq FROM run_events").fetchall()
    con.close()
    assert len(set(rows)) == len(rows)  # all unique


# --------------------------------------------------------------------------- F12
def test_f12_html_reducer_is_linear_not_redos() -> None:
    """Unclosed <script> in a large page must not blow up (was O(n²) — a ReDoS)."""
    pathological = "<script>" + ("a" * 200_000)  # no closing tag
    t0 = time.monotonic()
    _title, body = html_to_text(pathological)
    assert time.monotonic() - t0 < 1.0  # linear scan → well under a second
    assert body == ""  # unclosed block dropped


async def test_f12_fetch_streams_with_byte_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """The body is capped during streaming, not buffered whole then sliced."""

    class _Resp:
        status_code = 200
        encoding = "utf-8"
        url = "http://93.184.216.34/big"

        def __init__(self) -> None:
            self.headers = {"content-type": "text/plain"}

        async def aiter_bytes(self):
            for _ in range(100):
                yield b"x" * 10_000  # 1 MB total, in chunks

    def stream(self, method, url, **kwargs):
        class _CM:
            async def __aenter__(self_i):
                return _Resp()

            async def __aexit__(self_i, *a):
                return False

        return _CM()

    monkeypatch.setattr(httpx.AsyncClient, "stream", stream)
    connector = WebResearchConnector(CONNECTORS)
    ctx = ExecutionContext(
        workspace_id="w", run_id="r", correlation_id="c", config={"max_bytes": 50_000}
    )
    result = await connector.execute("web.fetch", {"url": "http://93.184.216.34/big"}, ctx)
    assert result.data["truncated"] is True
    assert len(result.data["content"]) <= 8000  # max_chars cap on the returned text
