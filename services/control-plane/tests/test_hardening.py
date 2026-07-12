"""Hardening from the review's design concerns:

- dry-run is a distinct connector capability (a connector without a real preview fails closed,
  never performs the effect during a "preview");
- runtime-registered connector tools are untrusted — their self-declared classification never
  earns auto-execution (registration is not a grant of trust).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from cockpit.connectors.base import (
    BaseConnector,
    ExecutionContext,
    HealthStatus,
    PreviewNotSupported,
    ToolResult,
)
from cockpit.connectors.local_files import LocalFilesConnector
from cockpit.enums import (
    Autonomy,
    ConnectorHealthState,
    ConnectorMode,
    ExecMode,
    PolicyKind,
    RiskLevel,
    ToolAccess,
)
from cockpit.events import get_bus
from cockpit.gateway import ToolGateway
from cockpit.ids import correlation_id, new_id
from cockpit.models import Connector, Run
from cockpit.policy import Outcome, PolicyContext, Rule, ToolSpec, evaluate
from cockpit.registry import get_registry


# ---------------------------------------------------------------- concern 2: trust
def _ext_read(trusted: bool) -> ToolSpec:
    return ToolSpec(
        tool_id="n8n.enrich",
        connector_slug="n8n",
        access=ToolAccess.READ,
        risk_level=RiskLevel.R1,
        external_side_effects=True,
        supports_dry_run=False,
        idempotent=False,
        trusted=trusted,
    )


def _ctx(**kw) -> PolicyContext:
    base = dict(
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
    base.update(kw)
    return PolicyContext(**base)


def test_untrusted_external_read_requires_approval() -> None:
    """A 'read-only' webhook the user registered is not auto-run on its own say-so."""
    d = evaluate(_ext_read(trusted=False), _ctx())
    assert d.outcome is Outcome.REQUIRE_APPROVAL


def test_trusted_external_read_still_auto_allows() -> None:
    d = evaluate(_ext_read(trusted=True), _ctx())
    assert d.outcome is Outcome.ALLOW


def test_untrusted_external_read_allowed_only_via_explicit_rule() -> None:
    d = evaluate(
        _ext_read(trusted=False),
        _ctx(rules=(Rule(kind=PolicyKind.ALLOW, tool_id="n8n.enrich"),)),
    )
    assert d.outcome is Outcome.ALLOW and "allowlist" in d.notes


def test_untrusted_external_read_denied_in_safe_mode() -> None:
    d = evaluate(_ext_read(trusted=False), _ctx(safe_mode=True))
    assert d.outcome is Outcome.DENY


def test_registered_n8n_tool_is_untrusted_and_external(workspace: dict) -> None:
    """Even read_only=True registration yields an untrusted, external, approval-gated tool."""
    from cockpit.db import db_session

    registry = get_registry()
    n8n = registry.connectors["n8n"]
    n8n.runtime_config = {"webhooks": [{"name": "enrich", "url": "https://x/y", "read_only": True}]}
    tool = n8n.get_tool("n8n.enrich")
    assert tool is not None
    assert tool.trusted is False
    assert tool.external_side_effects is True
    assert tool.approval == "required"
    del db_session


# ---------------------------------------------------------------- concern 1: preview
class _NoPreviewConnector(BaseConnector):
    slug = "noprev"

    def __init__(self) -> None:  # skip manifest loading
        self._manifest = None  # type: ignore[assignment]

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        return HealthStatus(ConnectorHealthState.OK)

    async def execute(self, tool_id, validated_input, ctx) -> ToolResult:
        return ToolResult(ok=True, data={}, external_confirmed=True)


def test_base_preview_refuses_by_default() -> None:
    connector = _NoPreviewConnector()
    assert connector.supports_preview() is False


async def test_base_preview_raises() -> None:
    connector = _NoPreviewConnector()
    with pytest.raises(PreviewNotSupported):
        await connector.preview("noprev.x", {}, ExecutionContext("ws", "r", "c"))


def test_local_files_preview_does_not_write_but_execute_does(workspace: dict, tmp_path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    connector = LocalFilesConnector.__new__(LocalFilesConnector)
    ctx = ExecutionContext(
        workspace_id=workspace["workspace_id"],
        run_id="r",
        correlation_id="c",
        roots=[root],
        settings=workspace["settings"],
    )
    target = root / "note.md"

    preview = connector._preview_write({"path": str(target), "content": "hi"}, ctx)
    assert preview.data["written"] is False
    assert not target.exists()  # preview performed no write
    assert "hi" in preview.data["diff"]

    connector._write({"path": str(target), "content": "hi"}, ctx)
    assert target.read_text() == "hi"


async def test_gateway_draft_write_routes_to_preview_no_effect(workspace: dict) -> None:
    """In draft mode the R3 external mock write runs as a preview — no event is created."""
    from cockpit.db import db_session
    from cockpit.workspace import update_workspace_settings

    registry = get_registry()
    gateway = ToolGateway(workspace["settings"], get_bus(), registry.connectors)
    google = registry.connectors["google-workspace"]
    google._created_events = []  # type: ignore[attr-defined]

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

    async with db_session() as session:
        run = Run(
            id=new_id("run"),
            workspace_id=workspace["workspace_id"],
            status="executing",
            mode="draft",
            correlation_id=correlation_id(),
        )
        session.add(run)
        await session.commit()
        run = await session.merge(run)
        result = await gateway.call_tool(
            session,
            run,
            "google.calendar.create_event",
            {"title": "X", "start": "2026-07-13T09:00:00Z", "end": "2026-07-13T10:00:00Z"},
            purpose="draft create",
        )
        await session.commit()

    assert result.ok
    assert result.data.get("created") is False  # preview, not real
    assert google._created_events == []  # no real effect performed
