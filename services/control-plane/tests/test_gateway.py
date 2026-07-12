"""Gateway: schema validation, approval pause/resume, idempotent replay, denial."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from cockpit.enums import ApprovalStatus, ToolCallStatus
from cockpit.events import get_bus
from cockpit.gateway import ApprovalPending, ToolDenied, ToolGateway
from cockpit.ids import correlation_id, new_id
from cockpit.models import Approval, Run, ToolCall
from cockpit.registry import get_registry


def make_gateway(app_env: dict) -> ToolGateway:
    registry = get_registry()
    return ToolGateway(app_env["settings"], get_bus(), registry.connectors)


async def make_run(workspace_id: str, **kw) -> Run:
    from cockpit.db import db_session

    async with db_session() as session:
        run = Run(
            id=new_id("run"),
            workspace_id=workspace_id,
            status="executing",
            mode=kw.pop("mode", "act"),
            correlation_id=correlation_id(),
            **kw,
        )
        session.add(run)
        await session.commit()
        return run


async def test_unknown_tool_denied(workspace: dict) -> None:
    gateway = make_gateway(workspace)
    from cockpit.db import db_session

    run = await make_run(workspace["workspace_id"])
    async with db_session() as session:
        run = await session.merge(run)
        with pytest.raises(ToolDenied, match="Unknown tool"):
            await gateway.call_tool(session, run, "nope.nothing", {}, purpose="x")


async def test_input_schema_violation_rejected(workspace: dict) -> None:
    gateway = make_gateway(workspace)
    from cockpit.db import db_session
    from cockpit.gateway import SchemaViolation

    run = await make_run(workspace["workspace_id"])
    async with db_session() as session:
        run = await session.merge(run)
        with pytest.raises(SchemaViolation):
            await gateway.call_tool(session, run, "local_files.read", {"nope": 1}, purpose="x")


async def test_read_allowed_and_recorded(workspace: dict) -> None:
    gateway = make_gateway(workspace)
    from cockpit.db import db_session

    run = await make_run(workspace["workspace_id"])
    async with db_session() as session:
        run = await session.merge(run)
        result = await gateway.call_tool(
            session,
            run,
            "local_files.list",
            {"root": str(workspace["ideas_dir"]), "glob": "*.md"},
            purpose="list ideas",
        )
        await session.commit()
        assert result.ok and len(result.data["entries"]) == 3
        call = await session.scalar(select(ToolCall).where(ToolCall.run_id == run.id))
        assert call is not None and call.status == ToolCallStatus.COMPLETED.value


async def test_write_requires_approval_then_executes_on_approve(workspace: dict) -> None:
    """The core security invariant: R2+ writes cannot execute before approval."""
    gateway = make_gateway(workspace)
    from cockpit.db import db_session

    target = workspace["ideas_dir"] / "note.md"
    run = await make_run(workspace["workspace_id"], mode="act")

    async with db_session() as session:
        run1 = await session.merge(run)
        with pytest.raises(ApprovalPending) as exc_info:
            await gateway.call_tool(
                session,
                run1,
                "local_files.write",
                {"path": str(target), "content": "hello"},
                purpose="write test note",
            )
        await session.commit()
    assert not target.exists(), "file must not exist before approval"

    async with db_session() as session:
        approval = await session.get(Approval, exc_info.value.approval_id)
        assert approval is not None and approval.status == ApprovalStatus.PENDING.value
        assert approval.diff_preview and "hello" in approval.diff_preview
        approval.status = ApprovalStatus.APPROVED.value
        call = await session.get(ToolCall, approval.tool_call_id)
        call.status = ToolCallStatus.APPROVED.value
        await session.commit()

    async with db_session() as session:
        run2 = await session.merge(run)
        result = await gateway.call_tool(
            session,
            run2,
            "local_files.write",
            {"path": str(target), "content": "hello"},
            purpose="write test note",
        )
        await session.commit()
    assert result.ok and target.read_text() == "hello"

    # replay: same call again returns recorded result without touching the file
    target.write_text("mutated externally")
    async with db_session() as session:
        run3 = await session.merge(run)
        replay = await gateway.call_tool(
            session,
            run3,
            "local_files.write",
            {"path": str(target), "content": "hello"},
            purpose="write test note",
        )
    assert replay.ok and "replayed" in replay.summary
    assert target.read_text() == "mutated externally", "replay must not re-execute the write"


async def test_denied_approval_raises_tool_denied(workspace: dict) -> None:
    gateway = make_gateway(workspace)
    from cockpit.db import db_session

    target = workspace["ideas_dir"] / "denied.md"
    run = await make_run(workspace["workspace_id"], mode="act")
    async with db_session() as session:
        run1 = await session.merge(run)
        with pytest.raises(ApprovalPending) as exc_info:
            await gateway.call_tool(
                session,
                run1,
                "local_files.write",
                {"path": str(target), "content": "x"},
                purpose="w",
            )
        await session.commit()
    async with db_session() as session:
        approval = await session.get(Approval, exc_info.value.approval_id)
        approval.status = ApprovalStatus.DENIED.value
        await session.commit()
    async with db_session() as session:
        run2 = await session.merge(run)
        with pytest.raises(ToolDenied):
            await gateway.call_tool(
                session,
                run2,
                "local_files.write",
                {"path": str(target), "content": "x"},
                purpose="w",
            )
    assert not target.exists()


async def test_safe_mode_denies_external_write(workspace: dict) -> None:
    """Even with the connector opened to read_write, Safe Mode blocks external effects."""
    gateway = make_gateway(workspace)
    from cockpit.db import db_session
    from cockpit.models import Connector

    async with db_session() as session:
        row = await session.scalar(
            select(Connector).where(
                Connector.workspace_id == workspace["workspace_id"],
                Connector.slug == "google-workspace",
            )
        )
        row.mode = "read_write"
        await session.commit()

    run = await make_run(workspace["workspace_id"], mode="act")
    async with db_session() as session:
        run = await session.merge(run)
        with pytest.raises(ToolDenied, match="Safe Mode"):
            await gateway.call_tool(
                session,
                run,
                "google.calendar.create_event",
                {"title": "x", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z"},
                purpose="create event",
            )


async def test_read_only_connector_denies_before_safe_mode(workspace: dict) -> None:
    """Mock connectors ship read-only: the connector toggle alone blocks writes."""
    gateway = make_gateway(workspace)
    from cockpit.db import db_session

    run = await make_run(workspace["workspace_id"], mode="act")
    async with db_session() as session:
        run = await session.merge(run)
        with pytest.raises(ToolDenied, match="read-only"):
            await gateway.call_tool(
                session,
                run,
                "google.calendar.create_event",
                {"title": "x", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z"},
                purpose="create event",
            )


async def test_path_containment_enforced(workspace: dict) -> None:
    gateway = make_gateway(workspace)
    from cockpit.db import db_session

    run = await make_run(workspace["workspace_id"])
    async with db_session() as session:
        run = await session.merge(run)
        result = await gateway.call_tool(
            session,
            run,
            "local_files.read",
            {"path": "/etc/passwd"},
            purpose="sneaky read",
        )
        assert result.ok is False
        assert "outside the configured roots" in (result.error or "")
