"""Home briefing — real local data only; demo-derived items are flagged (BUILD_BRIEF §Home)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import get_settings
from cockpit.models import (
    Approval,
    Artifact,
    Commitment,
    Connector,
    Project,
    Run,
    Skill,
    UserProfile,
)
from cockpit.workspace import get_workspace_settings


async def build_briefing(session: AsyncSession, workspace_id: str) -> dict[str, Any]:
    ws = await get_workspace_settings(session, workspace_id)
    profile = await session.scalar(
        select(UserProfile).where(UserProfile.workspace_id == workspace_id)
    )
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    pending_approvals = (
        await session.scalars(
            select(Approval)
            .where(Approval.workspace_id == workspace_id, Approval.status == "pending")
            .order_by(Approval.requested_at.desc())
        )
    ).all()
    active_runs = (
        await session.scalars(
            select(Run)
            .where(
                Run.workspace_id == workspace_id,
                Run.status.in_(
                    [
                        "queued",
                        "triaging",
                        "planning",
                        "awaiting_approval",
                        "executing",
                        "verifying",
                        "reviewing",
                    ]
                ),
            )
            .order_by(Run.created_at.desc())
        )
    ).all()
    recent_runs = (
        await session.scalars(
            select(Run)
            .where(
                Run.workspace_id == workspace_id,
                Run.status.in_(["completed", "failed", "cancelled", "interrupted"]),
            )
            .order_by(Run.finished_at.desc())
            .limit(5)
        )
    ).all()
    runs_today = (
        await session.scalar(
            select(func.count(Run.id)).where(
                Run.workspace_id == workspace_id, Run.created_at >= day_start
            )
        )
    ) or 0
    artifacts_week = (
        await session.scalar(
            select(func.count(Artifact.id)).where(
                Artifact.workspace_id == workspace_id, Artifact.created_at >= week_ago
            )
        )
    ) or 0
    commitments_due = (
        await session.scalars(
            select(Commitment)
            .where(
                Commitment.workspace_id == workspace_id,
                Commitment.status == "open",
                Commitment.due_at.is_not(None),
                Commitment.due_at <= now + timedelta(days=2),
            )
            .order_by(Commitment.due_at)
        )
    ).all()
    projects = (
        await session.scalars(
            select(Project).where(Project.workspace_id == workspace_id, Project.status == "active")
        )
    ).all()
    connectors = (
        await session.scalars(select(Connector).where(Connector.workspace_id == workspace_id))
    ).all()
    skills = (
        await session.scalars(
            select(Skill)
            .where(Skill.workspace_id == workspace_id, Skill.enabled == True)  # noqa: E712
            .order_by(Skill.name)
        )
    ).all()

    agenda = _demo_agenda() if ws.demo_mode else {"events": [], "demo": False}

    what_matters: list[dict[str, str]] = []
    if pending_approvals:
        what_matters.append(
            {
                "kind": "approvals",
                "text": f"{len(pending_approvals)} action(s) waiting for your approval",
                "href": "/approvals",
            }
        )
    for c in commitments_due[:3]:
        due = c.due_at.strftime("%a %H:%M") if c.due_at else ""
        what_matters.append(
            {"kind": "commitment", "text": f"Due {due}: {c.title}", "href": "/agenda"}
        )
    stale_cutoff = now - timedelta(days=10)
    stale = [p for p in projects if (p.updated_at or p.created_at) < stale_cutoff]
    if stale:
        what_matters.append(
            {
                "kind": "project",
                "text": f"{len(stale)} project(s) look stalled — run Project Pulse",
                "href": "/skills/project-pulse",
            }
        )
    interrupted = [r for r in recent_runs if r.status == "interrupted"]
    if interrupted:
        what_matters.append(
            {
                "kind": "run",
                "text": f"{len(interrupted)} run(s) were interrupted by a restart — resume them",
                "href": "/history",
            }
        )
    if not what_matters:
        what_matters.append(
            {
                "kind": "clear",
                "text": "Nothing urgent. A good moment for deep work or a Weekly Review.",
                "href": "/skills",
            }
        )

    suggestions: list[dict[str, str]] = []
    if not any(r.skill_slug == "morning-brief" and r.created_at >= day_start for r in recent_runs):
        suggestions.append({"skill": "morning-brief", "label": "Run your Morning Brief"})
    if stale:
        suggestions.append({"skill": "project-pulse", "label": "Check project movement"})
    if ws.bizideas_path or ws.demo_mode:
        suggestions.append({"skill": "business-idea-triage", "label": "Triage business ideas"})
    suggestions = suggestions[:3]

    return {
        "user_name": profile.user_name if profile else None,
        "assistant_name": profile.assistant_name if profile else "Otto",
        "now": now.isoformat(),
        "safe_mode": ws.safe_mode,
        "kill_switch": ws.kill_switch,
        "demo_mode": ws.demo_mode,
        "what_matters": what_matters,
        "approvals": {
            "pending": len(pending_approvals),
            "items": [
                {
                    "id": a.id,
                    "title": a.title,
                    "risk_level": a.risk_level,
                    "requested_at": a.requested_at.isoformat(),
                }
                for a in pending_approvals[:3]
            ],
        },
        "active_runs": [
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "kind": r.kind,
                "skill_slug": r.skill_slug,
            }
            for r in active_runs[:5]
        ],
        "recent_runs": [
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in recent_runs
        ],
        "suggestions": suggestions,
        "skills": [
            {
                "slug": s.slug,
                "name": s.name,
                "description": s.description,
                "autonomy": s.autonomy,
                "risk_level": s.risk_level,
            }
            for s in skills
        ],
        "agenda": agenda,
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "updated_at": (p.updated_at or p.created_at).isoformat(),
            }
            for p in projects[:6]
        ],
        "metrics": {
            "runs_today": runs_today,
            "approvals_pending": len(pending_approvals),
            "artifacts_week": artifacts_week,
            "connectors_ok": sum(1 for c in connectors if c.health in ("ok", "mock")),
            "connectors_total": len(connectors),
        },
        "connector_health": [
            {
                "slug": c.slug,
                "name": c.name,
                "health": c.health,
                "mode": c.mode,
                "enabled": c.enabled,
            }
            for c in connectors
        ],
    }


def _demo_agenda() -> dict[str, Any]:
    path = get_settings().demo_dir / "agenda.json"
    if not path.exists():
        return {"events": [], "demo": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"events": data.get("events", []), "demo": True}
