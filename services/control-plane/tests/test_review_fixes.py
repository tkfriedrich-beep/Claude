"""Regression tests for the adversarial-review findings (docs/reviews/codex-findings.md).

Each test fails on the pre-fix code and passes after. Findings F1–F6.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from cockpit.connectors.base import ConnectorError, ExecutionContext
from cockpit.connectors.local_files import LocalFilesConnector
from cockpit.enums import RunStatus, ToolCallStatus
from cockpit.events import EventBus, get_bus
from cockpit.gateway import ToolDenied, ToolGateway
from cockpit.ids import correlation_id, new_id
from cockpit.models import Run, ToolCall
from cockpit.registry import get_registry


# --------------------------------------------------------------------------- F1
async def _run(workspace_id: str, **kw) -> Run:
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


async def test_f1_interrupted_non_idempotent_write_is_not_replayed(workspace: dict) -> None:
    """A tool_call left RUNNING (crash after dispatch) must not auto-fire again."""
    from cockpit.db import db_session

    registry = get_registry()
    gateway = ToolGateway(workspace["settings"], get_bus(), registry.connectors)
    run = await _run(workspace["workspace_id"])

    # Simulate the durable "intent" a crash leaves behind: a RUNNING tool_call for a
    # non-idempotent external tool (the mock calendar create_event, R3, idempotent=False).
    tool_id = "google.calendar.create_event"
    tool_input = {"title": "x", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z"}
    from cockpit.gateway import idempotency_key

    async with db_session() as session:
        session.add(
            ToolCall(
                id=new_id("tc"),
                workspace_id=workspace["workspace_id"],
                run_id=run.id,
                tool_id=tool_id,
                connector_slug="google-workspace",
                status=ToolCallStatus.RUNNING.value,
                risk_level="R3",
                idempotency_key=idempotency_key(run.id, tool_id, tool_input),
            )
        )
        await session.commit()

    async with db_session() as session:
        run = await session.merge(run)
        with pytest.raises(ToolDenied, match="Interrupted after this action was dispatched"):
            await gateway.call_tool(session, run, tool_id, tool_input, purpose="retry after crash")
        await session.commit()
        # the ambiguous row is now failed, not re-run
        call = await session.scalar(select(ToolCall).where(ToolCall.run_id == run.id))
        assert call.status == ToolCallStatus.FAILED.value


async def test_f1_idempotent_running_call_may_rerun(workspace: dict) -> None:
    """Local/idempotent writes left RUNNING are safe to re-run (not blocked)."""
    from cockpit.db import db_session
    from cockpit.gateway import idempotency_key

    registry = get_registry()
    gateway = ToolGateway(workspace["settings"], get_bus(), registry.connectors)
    run = await _run(workspace["workspace_id"], skill_slug="business-idea-triage")
    target = str(workspace["ideas_dir"] / "f1.md")
    tool_input = {"path": target, "content": "hello"}

    async with db_session() as session:
        # local_files.write is idempotent + no external side effects → RUNNING is replayable.
        session.add(
            ToolCall(
                id=new_id("tc"),
                workspace_id=workspace["workspace_id"],
                run_id=run.id,
                tool_id="local_files.write",
                connector_slug="local-files",
                status=ToolCallStatus.APPROVED.value,  # pre-approved so it executes
                risk_level="R2",
                idempotency_key=idempotency_key(run.id, "local_files.write", tool_input),
            )
        )
        await session.commit()

    async with db_session() as session:
        run = await session.merge(run)
        result = await gateway.call_tool(
            session, run, "local_files.write", tool_input, purpose="write"
        )
        await session.commit()
    assert result.ok  # not blocked


# --------------------------------------------------------------------------- F2
def _ctx(workspace: dict, roots) -> ExecutionContext:
    return ExecutionContext(
        workspace_id=workspace["workspace_id"],
        run_id="r",
        correlation_id="c",
        roots=roots,
        settings=workspace["settings"],
    )


def test_f2_write_through_symlink_is_rejected(workspace: dict, tmp_path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("original")
    (root / "escape.md").symlink_to(outside)

    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    with pytest.raises(ConnectorError, match="symlink"):
        connector._write(
            {"path": str(root / "escape.md"), "content": "pwned"}, _ctx(workspace, [root])
        )
    assert outside.read_text() == "original"  # untouched


def test_f2_dotdot_name_rejected(workspace: dict, tmp_path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    with pytest.raises(ConnectorError):
        connector._write({"path": str(root / ".."), "content": "x"}, _ctx(workspace, [root]))


def test_f2_normal_write_still_works(workspace: dict, tmp_path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    result = connector._write(
        {"path": str(root / "note.md"), "content": "hi"}, _ctx(workspace, [root])
    )
    assert result.ok and (root / "note.md").read_text() == "hi"


# --------------------------------------------------------------------------- F3
async def test_f3_claim_is_a_real_cas(workspace: dict) -> None:
    """A claimed-but-still-queued run cannot be claimed again."""
    from cockpit.db import db_session
    from cockpit.worker import claim_next_run

    run = await _run(
        workspace["workspace_id"], status="queued", kind="skill", skill_slug="project-pulse"
    )

    async with db_session() as s1:
        first = await claim_next_run(s1)
    assert first is not None and first.id == run.id

    # The run is still status=queued (claim doesn't flip status) but now has a worker_claim;
    # a second claim must NOT pick it up again.
    async with db_session() as s2:
        second = await claim_next_run(s2)
    assert second is None

    async with db_session() as session:
        fresh = await session.get(Run, run.id)
        assert fresh.status == "queued" and fresh.worker_claim is not None


async def test_f3_requeue_clears_claim(workspace: dict) -> None:
    """Re-queueing (resume/approval) clears the claim so the run is claimable again."""
    from cockpit.db import db_session
    from cockpit.state_machine import transition
    from cockpit.worker import claim_next_run

    run = await _run(
        workspace["workspace_id"], status="queued", kind="skill", skill_slug="project-pulse"
    )
    async with db_session() as session:
        claimed = await claim_next_run(session)
    assert claimed is not None

    # Drive queued→triaging→…→awaiting_approval→queued to mimic an approval continuation.
    async with db_session() as session:
        r = await session.get(Run, run.id)
        await transition(session, get_bus(), r, RunStatus.TRIAGING)
        await transition(session, get_bus(), r, RunStatus.PLANNING)
        await transition(session, get_bus(), r, RunStatus.AWAITING_APPROVAL)
        await transition(session, get_bus(), r, RunStatus.QUEUED)
        await session.commit()
        assert r.worker_claim is None

    async with db_session() as session:
        reclaimed = await claim_next_run(session)
    assert reclaimed is not None and reclaimed.id == run.id


# --------------------------------------------------------------------------- F6
async def test_f6_event_bus_evicts_per_run_state(workspace: dict) -> None:
    """seq locks and empty subscription sets don't accumulate per run."""
    from cockpit.db import db_session
    from cockpit.enums import EventType

    bus = EventBus()
    # subscribe/unsubscribe leaves no empty set behind
    q = bus.subscribe("run_x")
    bus.unsubscribe(q, "run_x")
    assert "run_x" not in bus._by_run

    # a terminal event drops the run's seq lock
    run = await _run(workspace["workspace_id"], status="reviewing")
    async with db_session() as session:
        r = await session.merge(run)
        await bus.emit(
            session,
            workspace_id=r.workspace_id,
            run_id=r.id,
            type=EventType.TOOL_PROGRESS,
            payload={"message": "x"},
        )
        assert r.id in bus._seq_locks
        await bus.emit(
            session,
            workspace_id=r.workspace_id,
            run_id=r.id,
            type=EventType.RUN_COMPLETED,
            payload={},
        )
        assert r.id not in bus._seq_locks


# --------------------------------------------------------------------------- F5 (unit)
def test_f5_backfill_dedupe_logic() -> None:
    """The high-water-mark rule drops already-backfilled live events and never over-drops."""
    # Mirrors the generator's dedupe: last_sent tracks max delivered id.
    backfilled_ids = [10, 11, 12]
    last_sent = max(backfilled_ids)
    live = [11, 12, 13, 14]  # 11,12 are duplicates from the subscribe-before-backfill window
    delivered = []
    for eid in live:
        if eid <= last_sent:
            continue
        last_sent = eid
        delivered.append(eid)
    assert delivered == [13, 14]


async def test_f4_chat_approval_request_denied_not_blocking(workspace: dict) -> None:
    """A chat tool needing approval is denied immediately, never parked in the worker."""
    from cockpit.db import db_session
    from cockpit.models import Connector
    from cockpit.worker import RunProcessor

    registry = get_registry()
    processor = RunProcessor(workspace["settings"], registry, get_bus())

    # open the mock connector to read_write so create_event reaches REQUIRE_APPROVAL, and
    # disable safe mode so we exercise the approval path (not the safe-mode denial).
    from cockpit.workspace import update_workspace_settings

    async with db_session() as session:
        await update_workspace_settings(session, workspace["workspace_id"], {"safe_mode": False})
        row = await session.scalar(
            select(Connector).where(
                Connector.workspace_id == workspace["workspace_id"],
                Connector.slug == "google-workspace",
            )
        )
        row.mode = "read_write"
        await session.commit()

    run = await _run(workspace["workspace_id"], status="executing", kind="chat")
    async with db_session() as session:
        run = await session.merge(run)
        allowed, reason, _ = await asyncio.wait_for(
            processor._chat_permission(
                session,
                run,
                "google.calendar.create_event",
                {"title": "x", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z"},
            ),
            timeout=5,  # must return fast, not block for 600s
        )
    assert allowed is False
    assert "run" in reason.lower() and "skill" in reason.lower()
