"""Health, doctor, onboarding, settings, domains, policies, usage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import cockpit
from cockpit.api.deps import get_session, get_workspace
from cockpit.config import get_settings
from cockpit.enums import DEFAULT_DOMAINS
from cockpit.ids import new_id
from cockpit.models import (
    AgentProfile,
    ContextPack,
    Domain,
    PolicyRule,
    Run,
    UserProfile,
    Workspace,
)
from cockpit.registry import get_registry
from cockpit.schemas import (
    DomainOut,
    DomainPatchRequest,
    OnboardingRequest,
    PolicyCreateRequest,
    PolicyOut,
    SettingsPatchRequest,
)
from cockpit.workspace import get_workspace_settings, update_workspace_settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": cockpit.__version__, "time": datetime.now(UTC).isoformat()}


@router.get("/doctor")
async def doctor(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from cockpit.doctor import run_checks

    return await run_checks(session)


@router.get("/onboarding/status")
async def onboarding_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    ws = await session.scalar(select(Workspace).limit(1))
    if ws is None:
        return {"completed": False}
    profile = await session.scalar(select(UserProfile).where(UserProfile.workspace_id == ws.id))
    return {
        "completed": bool(profile and profile.onboarded_at),
        "workspace_id": ws.id,
        "user_name": profile.user_name if profile else None,
        "assistant_name": profile.assistant_name if profile else "Otto",
    }


@router.post("/onboarding", status_code=201)
async def onboarding(
    body: OnboardingRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    ws = await session.scalar(select(Workspace).limit(1))
    if ws is None:
        ws = Workspace(id=new_id("ws"), name=f"{body.user_name}'s Cockpit", settings={})
        session.add(ws)
        await session.flush()

    settings_patch: dict[str, Any] = {
        "safe_mode": body.safe_mode,
        "demo_mode": body.enable_demo_data,
        "provider": body.provider,
        "default_autonomy": body.default_autonomy,
    }
    if body.vault_path:
        settings_patch["vault_path"] = body.vault_path
    elif body.enable_demo_data:
        settings_patch["vault_path"] = str(get_settings().demo_dir / "vault")
    if body.bizideas_path:
        settings_patch["bizideas_path"] = body.bizideas_path
    elif body.enable_demo_data:
        settings_patch["bizideas_path"] = str(get_settings().demo_dir / "bizideas")
    await update_workspace_settings(session, ws.id, settings_patch)

    profile = await session.scalar(select(UserProfile).where(UserProfile.workspace_id == ws.id))
    if profile is None:
        profile = UserProfile(id=new_id("usr"), workspace_id=ws.id, user_name=body.user_name)
        session.add(profile)
    profile.user_name = body.user_name
    profile.assistant_name = body.assistant_name or "Otto"
    profile.timezone = body.timezone
    profile.onboarded_at = datetime.now(UTC)

    agent = await session.scalar(select(AgentProfile).where(AgentProfile.workspace_id == ws.id))
    if agent is None:
        session.add(
            AgentProfile(
                id=new_id("agt"),
                workspace_id=ws.id,
                name=profile.assistant_name,
                provider=body.provider,
            )
        )

    existing_domains = {
        d.key
        for d in (await session.scalars(select(Domain).where(Domain.workspace_id == ws.id))).all()
    }
    for spec in DEFAULT_DOMAINS:
        if spec["key"] not in existing_domains:
            session.add(
                Domain(
                    id=new_id("dom"),
                    workspace_id=ws.id,
                    key=str(spec["key"]),
                    name=str(spec["name"]),
                    enabled=bool(spec["enabled"]),
                    read_only=spec["sensitivity"] == "high",
                    sensitivity=str(spec["sensitivity"]),
                )
            )

    if not (
        await session.scalars(select(ContextPack).where(ContextPack.workspace_id == ws.id))
    ).first():
        session.add(
            ContextPack(
                id=new_id("cpk"),
                workspace_id=ws.id,
                name="Everything local",
                description="All configured local sources (vault, ideas folder, demo data).",
                sources=[{"type": "roots", "value": "all"}],
            )
        )

    registry = get_registry()
    await registry.sync_workspace(session, ws.id)
    await registry.run_health_checks(session, ws.id)
    await session.commit()

    if body.enable_demo_data:
        from cockpit.demo import seed_demo_content

        await seed_demo_content(ws.id)

    return {"workspace_id": ws.id, "completed": True}


@router.get("/settings")
async def get_settings_endpoint(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = await get_workspace_settings(session, workspace.id)
    profile = await session.scalar(
        select(UserProfile).where(UserProfile.workspace_id == workspace.id)
    )
    registry = get_registry()
    from cockpit.runtime import STUB_PROVIDERS
    from cockpit.runtime.claude import ClaudeAgentRuntime

    claude_ok, claude_detail = ClaudeAgentRuntime().available()
    return {
        "workspace_id": workspace.id,
        "user_name": profile.user_name if profile else None,
        "assistant_name": profile.assistant_name if profile else "Otto",
        "safe_mode": ws.safe_mode,
        "kill_switch": ws.kill_switch,
        "demo_mode": ws.demo_mode,
        "theme": ws.theme,
        "default_mode": ws.default_mode,
        "provider": ws.provider,
        "vault_path": ws.vault_path,
        "bizideas_path": ws.bizideas_path,
        "daily_budget_usd": ws.daily_budget_usd,
        "run_budget_usd": ws.run_budget_usd,
        "data_dir": str(get_settings().data_dir),
        "providers": {
            "mock": {"available": True, "detail": "Deterministic offline runtime."},
            "claude": {"available": claude_ok, "detail": claude_detail},
            **{k: {"available": False, "detail": v} for k, v in STUB_PROVIDERS.items()},
        },
        "skills_loaded": len(registry.skills),
    }


@router.patch("/settings")
async def patch_settings(
    body: SettingsPatchRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    patch = body.model_dump(exclude_none=True)
    await update_workspace_settings(session, workspace.id, patch)
    registry = get_registry()
    await registry.refresh_runtime_config(session, workspace.id)
    await session.commit()
    return {"ok": True, "applied": patch}


@router.get("/domains", response_model=list[DomainOut])
async def list_domains(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[Domain]:
    return list(
        (
            await session.scalars(
                select(Domain).where(Domain.workspace_id == workspace.id).order_by(Domain.name)
            )
        ).all()
    )


@router.patch("/domains/{key}", response_model=DomainOut)
async def patch_domain(
    key: str,
    body: DomainPatchRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> Domain:
    domain = await session.scalar(
        select(Domain).where(Domain.workspace_id == workspace.id, Domain.key == key)
    )
    if domain is None:
        raise HTTPException(404, f"Unknown domain {key}")
    if body.enabled is not None:
        domain.enabled = body.enabled
    if body.read_only is not None:
        if domain.sensitivity == "high" and body.read_only is False:
            raise HTTPException(
                400, "High-sensitivity domains stay read-only in the MVP (see THREAT_MODEL)."
            )
        domain.read_only = body.read_only
    await session.commit()
    return domain


@router.get("/policies", response_model=list[PolicyOut])
async def list_policies(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[PolicyRule]:
    return list(
        (
            await session.scalars(select(PolicyRule).where(PolicyRule.workspace_id == workspace.id))
        ).all()
    )


@router.post("/policies", response_model=PolicyOut, status_code=201)
async def create_policy(
    body: PolicyCreateRequest,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> PolicyRule:
    if not (body.tool_id or body.connector_slug or body.skill_slug):
        raise HTTPException(400, "A policy rule needs a tool, connector, or skill target.")
    rule = PolicyRule(
        id=new_id("pol"),
        workspace_id=workspace.id,
        name=body.name,
        kind=body.kind,
        tool_id=body.tool_id,
        connector_slug=body.connector_slug,
        skill_slug=body.skill_slug,
        note=body.note,
    )
    session.add(rule)
    await session.commit()
    return rule


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: str,
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await session.get(PolicyRule, policy_id)
    if rule is None or rule.workspace_id != workspace.id:
        raise HTTPException(404, "Policy not found")
    await session.delete(rule)
    await session.commit()


@router.get("/usage")
async def usage(
    workspace: Workspace = Depends(get_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    async def agg(since: datetime) -> dict[str, Any]:
        row = (
            await session.execute(
                select(
                    func.count(Run.id),
                    func.coalesce(func.sum(Run.cost_usd), 0.0),
                    func.coalesce(func.sum(Run.tokens_in), 0),
                    func.coalesce(func.sum(Run.tokens_out), 0),
                    func.coalesce(func.sum(Run.steps), 0),
                ).where(Run.workspace_id == workspace.id, Run.created_at >= since)
            )
        ).one()
        return {
            "runs": row[0],
            "cost_usd": round(row[1], 4),
            "tokens_in": row[2],
            "tokens_out": row[3],
            "tool_calls": row[4],
        }

    ws = await get_workspace_settings(session, workspace.id)
    return {
        "today": await agg(day_start),
        "week": await agg(week_ago),
        "budgets": {"daily_usd": ws.daily_budget_usd, "per_run_usd": ws.run_budget_usd},
    }
