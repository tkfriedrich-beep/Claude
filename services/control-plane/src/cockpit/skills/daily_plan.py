"""Daily Plan — realistic priority sequence and time blocks. Calendar changes stay drafts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from cockpit.models import Commitment, Project
from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillResult


class DailyPlanExecutor(BaseSkillExecutor):
    slug = "daily-plan"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "Load agenda and open commitments",
                "Sequence priorities",
                "Propose time blocks (drafts only)",
            ],
            expected_tools=["google.calendar.list_events"],
            side_effects_expected=False,
            success_checks=["Plan artifact exists", "No calendar mutations"],
        )

    async def execute(self) -> SkillResult:
        run = self.ctx.run
        cal = await self.ctx.call_tool(
            "google.calendar.list_events", {}, purpose="Loading today's fixed events"
        )
        events = cal.data.get("events", []) if cal.ok else []
        is_demo = bool(cal.ok and cal.data.get("demo"))

        now = datetime.now(UTC)
        commitments = (
            await self.ctx.session.scalars(
                select(Commitment)
                .where(Commitment.workspace_id == run.workspace_id, Commitment.status == "open")
                .order_by(Commitment.due_at.is_(None), Commitment.due_at)
            )
        ).all()
        projects = (
            await self.ctx.session.scalars(
                select(Project).where(
                    Project.workspace_id == run.workspace_id, Project.status == "active"
                )
            )
        ).all()

        # Deterministic, honest sequencing: due-dated commitments first, then one deep-work
        # block per active project, capped to a realistic day.
        blocks: list[dict[str, Any]] = []
        cursor = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        for c in commitments[:3]:
            blocks.append(
                {
                    "start": cursor.strftime("%H:%M"),
                    "minutes": 45,
                    "focus": f"Commitment: {c.title}",
                    "why": f"due {c.due_at.strftime('%a') if c.due_at else 'soon'}",
                }
            )
            cursor += timedelta(minutes=60)
        for p in projects[:2]:
            blocks.append(
                {
                    "start": cursor.strftime("%H:%M"),
                    "minutes": 90,
                    "focus": f"Deep work: {p.name}",
                    "why": "active project needing movement",
                }
            )
            cursor += timedelta(minutes=105)

        date_str = now.strftime("%A, %B %d")
        md = [f"# Daily Plan — {date_str}", ""]
        if is_demo:
            md += [
                "> ⚠ Fixed events come from **demo data** until Google Workspace is connected.",
                "",
            ]
        md.append("## Fixed events")
        md += [
            f"- {e.get('start', '')[:16].replace('T', ' ')} — {e.get('title')}" for e in events[:8]
        ] or ["_None._"]
        md += ["", "## Proposed blocks (drafts — nothing is scheduled without your approval)"]
        for b in blocks:
            md.append(f"- **{b['start']}** ({b['minutes']} min) — {b['focus']} · _{b['why']}_")
        if not blocks:
            md.append("_No open commitments or active projects to schedule._")

        data = {
            "date": date_str,
            "fixed_events": events,
            "agenda_is_demo": is_demo,
            "blocks": blocks,
        }
        return SkillResult(
            summary_md=f"Proposed {len(blocks)} time blocks around {len(events)} fixed events"
            f"{' (demo agenda)' if is_demo else ''}. All blocks are drafts.",
            data=data,
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title=f"Daily Plan — {date_str}",
                    filename="daily-plan.md",
                    content="\n".join(md),
                ),
                ArtifactSpec(
                    kind="json",
                    title="Daily Plan data",
                    filename="daily-plan.json",
                    content=json.dumps(data, indent=2, ensure_ascii=False, default=str),
                    mime="application/json",
                ),
            ],
            sources=[
                {
                    "label": "Demo calendar" if is_demo else "Calendar",
                    "reference": "data/demo/agenda.json" if is_demo else "google-workspace",
                }
            ],
        )
