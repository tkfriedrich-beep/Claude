"""Skills, connectors, automations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.api.deps import get_session, get_workspace
from cockpit.connectors.base import ExecutionContext
from cockpit.enums import EventType, RunStatus
from cockpit.events import get_bus
from cockpit.ids import correlation_id, new_id
from cockpit.models import Connector, ConnectorTool, Run, Schedule, Skill, Workspace
from cockpit.registry import get_registry
from cockpit.schemas import (
    AutomationCreateRequest,
    AutomationPatchRequest,
    ConnectorOut,
    ConnectorPatchRequest,
    ConnectorRegisterRequest,
    ConnectorToolOut,
    RunOut,
    ScheduleOut,
    SkillOut,
    SkillPatchRequest,
)
from cockpit.workspace import allowed_roots_for, get_workspace_settings

router = APIRouter(tags=["catalog"])


# ---------------------------------------------------------------- skills


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Skill]:
    return list(
        (
            await session.scalars(
                select(Skill).where(Skill.workspace_id == workspace.id).order_by(Skill.name)
            )
        ).all()
    )


@router.get("/skills/{slug}", response_model=SkillOut)
async def get_skill(
    slug: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Skill:
    skill = await session.scalar(
        select(Skill).where(Skill.workspace_id == workspace.id, Skill.slug == slug)
    )
    if skill is None:
        raise HTTPException(404, f"Skill “{slug}” not found")
    return skill


@router.patch("/skills/{slug}", response_model=SkillOut)
async def patch_skill(
    slug: str,
    body: SkillPatchRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Skill:
    skill = await get_skill(slug, workspace, session)
    if body.autonomy is not None:
        # Autonomy changes are always explicit human acts (never automatic promotion).
        skill.autonomy = body.autonomy
    if body.enabled is not None:
        skill.enabled = body.enabled
    await session.commit()
    return skill


@router.post("/skills/{slug}/run", response_model=RunOut, status_code=201)
async def run_skill(
    slug: str,
    request: Request,
    body: dict[str, Any] | None = None,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    skill = await get_skill(slug, workspace, session)
    if not skill.enabled:
        raise HTTPException(409, f"Skill “{skill.name}” is disabled.")
    ws = await get_workspace_settings(session, workspace.id)
    if ws.kill_switch:
        raise HTTPException(423, "Kill switch is engaged.")
    payload = body or {}
    run = Run(
        id=new_id("run"),
        workspace_id=workspace.id,
        kind="skill",
        status=RunStatus.QUEUED.value,
        title=skill.name,
        skill_slug=slug,
        input=payload.get("input", {}),
        mode=payload.get("mode", ws.default_mode),
        domain_key=(skill.domains[0] if skill.domains else None),
        correlation_id=request.headers.get("X-Correlation-Id") or correlation_id(),
    )
    session.add(run)
    await session.flush()
    await get_bus().emit(
        session,
        workspace_id=workspace.id,
        run_id=run.id,
        type=EventType.RUN_QUEUED,
        payload={"skill": slug},
    )
    await session.commit()
    return run


# ---------------------------------------------------------------- connectors


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Connector]:
    return list(
        (
            await session.scalars(
                select(Connector)
                .where(Connector.workspace_id == workspace.id)
                .order_by(Connector.category, Connector.name)
            )
        ).all()
    )


@router.get("/connectors/{slug}", response_model=ConnectorOut)
async def get_connector(
    slug: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Connector:
    connector = await session.scalar(
        select(Connector).where(Connector.workspace_id == workspace.id, Connector.slug == slug)
    )
    if connector is None:
        raise HTTPException(404, f"Connector “{slug}” not found")
    return connector


@router.get("/connectors/{slug}/tools", response_model=list[ConnectorToolOut])
async def connector_tools(
    slug: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[ConnectorTool]:
    return list(
        (
            await session.scalars(
                select(ConnectorTool).where(
                    ConnectorTool.workspace_id == workspace.id, ConnectorTool.connector_slug == slug
                )
            )
        ).all()
    )


@router.post("/connectors/{slug}/health", response_model=ConnectorOut)
async def check_connector_health(
    slug: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Connector:
    row = await get_connector(slug, workspace, session)
    registry = get_registry()
    instance = registry.connectors.get(slug)
    if instance is None:
        raise HTTPException(404, "Connector implementation missing")
    await registry.refresh_runtime_config(session, workspace.id)
    ctx = ExecutionContext(
        workspace_id=workspace.id,
        run_id="health",
        correlation_id="health",
        roots=await allowed_roots_for(workspace.id),
        config=getattr(instance, "runtime_config", {}) or {},
        settings=registry.settings,
    )
    try:
        status = await instance.health_check(ctx)
        row.health = status.state.value
        row.health_detail = status.detail
        if status.state.value in ("ok", "mock"):
            row.last_success_at = datetime.now(UTC)
    except Exception as exc:
        row.health = "unavailable"
        row.health_detail = f"health check crashed: {exc}"
    await session.commit()
    return row


@router.patch("/connectors/{slug}", response_model=ConnectorOut)
async def patch_connector(
    slug: str,
    body: ConnectorPatchRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Connector:
    connector = await get_connector(slug, workspace, session)
    if body.enabled is not None:
        connector.enabled = body.enabled
    if body.mode is not None:
        connector.mode = body.mode
    if body.config is not None:
        _reject_secretlike(body.config)
        connector.config = body.config
    await get_registry().refresh_runtime_config(session, workspace.id)
    await session.commit()
    return connector


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
async def register_connector_resource(
    body: ConnectorRegisterRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Connector:
    """Register an n8n webhook or MCP server under the respective connector."""
    if body.kind == "n8n_webhook":
        if not body.url:
            raise HTTPException(400, "url is required for an n8n webhook")
        connector = await get_connector("n8n", workspace, session)
        hooks = list(connector.config.get("webhooks", []))
        if any(h["name"] == body.name for h in hooks):
            raise HTTPException(409, f"Webhook “{body.name}” already registered")
        hooks.append(
            {
                "name": body.name,
                "url": body.url,
                "secret_env": body.secret_env,
                "input_schema": body.input_schema or {"type": "object"},
                "output_schema": body.output_schema or {"type": "object"},
                "read_only": body.read_only,
                "supports_dry_run": body.supports_dry_run,
                "description": body.description,
            }
        )
        connector.config = {**connector.config, "webhooks": hooks}
    else:
        connector = await get_connector("mcp", workspace, session)
        servers = list(connector.config.get("servers", []))
        if any(s["name"] == body.name for s in servers):
            raise HTTPException(409, f"MCP server “{body.name}” already registered")
        entry: dict[str, Any] = {
            "name": body.name,
            "transport": body.transport or "stdio",
            "enabled": True,
            "description": body.description,
        }
        if entry["transport"] == "stdio":
            if not body.command:
                raise HTTPException(400, "command is required for a stdio MCP server")
            entry["command"] = body.command
            entry["args"] = body.args
            registry = get_registry()
            instance = registry.connectors.get("mcp")
            try:
                from cockpit.connectors.mcp import discover_stdio_tools

                entry["discovered_tools"] = await discover_stdio_tools(entry, timeout=10)
            except Exception as exc:
                entry["discovered_tools"] = []
                entry["discovery_error"] = str(exc)[:300]
            del instance  # discovery result stored; runtime config refresh follows
        servers.append(entry)
        connector.config = {**connector.config, "servers": servers}

    await get_registry().refresh_runtime_config(session, workspace.id)
    await session.commit()
    return connector


def _reject_secretlike(config: dict[str, Any]) -> None:
    import json as _json

    from cockpit.logging import SENSITIVE_VALUE_RE

    if SENSITIVE_VALUE_RE.search(_json.dumps(config)):
        raise HTTPException(
            400,
            "That config contains something that looks like a credential. Secrets belong in "
            "environment variables (SecretStore), referenced by name — never in the database.",
        )


# ---------------------------------------------------------------- automations


@router.get("/automations", response_model=list[ScheduleOut])
async def list_automations(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Schedule]:
    return list(
        (
            await session.scalars(
                select(Schedule)
                .where(Schedule.workspace_id == workspace.id)
                .order_by(Schedule.created_at)
            )
        ).all()
    )


@router.post("/automations", response_model=ScheduleOut, status_code=201)
async def create_automation(
    body: AutomationCreateRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Schedule:
    skill = await session.scalar(
        select(Skill).where(Skill.workspace_id == workspace.id, Skill.slug == body.skill_slug)
    )
    if skill is None:
        raise HTTPException(404, f"Skill “{body.skill_slug}” not found")
    if not skill.manifest.get("supports_schedule", True):
        raise HTTPException(409, f"Skill “{skill.name}” does not support scheduling.")
    schedule = Schedule(
        id=new_id("sch"),
        workspace_id=workspace.id,
        skill_slug=body.skill_slug,
        name=body.name or f"{skill.name} (scheduled)",
        interval_minutes=body.interval_minutes,
        shadow_mode=body.shadow_mode,  # Shadow Mode is the default for new automations
        input=body.input,
        next_run_at=datetime.now(UTC) + timedelta(minutes=body.start_in_minutes),
    )
    session.add(schedule)
    await session.commit()
    return schedule


@router.patch("/automations/{schedule_id}", response_model=ScheduleOut)
async def patch_automation(
    schedule_id: str,
    body: AutomationPatchRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Schedule:
    schedule = await session.get(Schedule, schedule_id)
    if schedule is None or schedule.workspace_id != workspace.id:
        raise HTTPException(404, "Automation not found")
    if body.enabled is not None:
        schedule.enabled = body.enabled
    if body.shadow_mode is not None:
        schedule.shadow_mode = body.shadow_mode
    if body.interval_minutes is not None:
        schedule.interval_minutes = body.interval_minutes
        schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=body.interval_minutes)
    await session.commit()
    return schedule


@router.post("/automations/{schedule_id}/run-now", response_model=RunOut, status_code=201)
async def run_automation_now(
    schedule_id: str,
    shadow: bool | None = None,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Run:
    schedule = await session.get(Schedule, schedule_id)
    if schedule is None or schedule.workspace_id != workspace.id:
        raise HTTPException(404, "Automation not found")
    is_shadow = schedule.shadow_mode if shadow is None else shadow
    run = Run(
        id=new_id("run"),
        workspace_id=workspace.id,
        kind="skill",
        status=RunStatus.QUEUED.value,
        title=f"{schedule.name} (manual{', shadow' if is_shadow else ''})",
        skill_slug=schedule.skill_slug,
        schedule_id=schedule.id,
        input=schedule.input or {},
        mode="draft" if is_shadow else "act",
        shadow=is_shadow,
        correlation_id=correlation_id(),
    )
    session.add(run)
    await session.flush()
    schedule.last_run_id = run.id
    schedule.last_run_at = datetime.now(UTC)
    await get_bus().emit(
        session,
        workspace_id=workspace.id,
        run_id=run.id,
        type=EventType.RUN_QUEUED,
        payload={"schedule": schedule.name, "shadow": is_shadow},
    )
    await session.commit()
    return run
