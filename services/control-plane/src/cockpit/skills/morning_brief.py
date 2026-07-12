"""Morning Brief — agenda, commitments, projects, notable changes. Demo data clearly labeled."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from cockpit.models import Approval, Commitment, Project
from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillResult


class MorningBriefExecutor(BaseSkillExecutor):
    slug = "morning-brief"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "Fetch today's agenda",
                "Collect due commitments",
                "Check project movement",
                "Compose the brief",
            ],
            expected_tools=["google.calendar.list_events", "obsidian.recent_changes"],
            side_effects_expected=False,
            success_checks=["Brief artifact exists", "Demo data labeled"],
        )

    async def execute(self) -> SkillResult:
        run = self.ctx.run
        agenda_events: list[dict[str, Any]] = []
        agenda_is_demo = False
        cal = await self.ctx.call_tool(
            "google.calendar.list_events",
            {},
            purpose="Fetching today's calendar",
        )
        if cal.ok:
            agenda_events = cal.data.get("events", [])
            agenda_is_demo = bool(cal.data.get("demo"))

        now = datetime.now(UTC)
        commitments = (
            await self.ctx.session.scalars(
                select(Commitment)
                .where(Commitment.workspace_id == run.workspace_id, Commitment.status == "open")
                .order_by(Commitment.due_at)
            )
        ).all()
        due_soon = [c for c in commitments if c.due_at and c.due_at <= now + timedelta(days=2)]
        projects = (
            await self.ctx.session.scalars(
                select(Project).where(
                    Project.workspace_id == run.workspace_id, Project.status == "active"
                )
            )
        ).all()
        pending_approvals = (
            await self.ctx.session.scalars(
                select(Approval).where(
                    Approval.workspace_id == run.workspace_id, Approval.status == "pending"
                )
            )
        ).all()

        changes = await self.ctx.call_tool(
            "obsidian.recent_changes",
            {"days": 2},
            purpose="Checking what changed in your notes",
        )
        changed_notes = changes.data.get("changed", [])[:6] if changes.ok else []

        date_str = now.strftime("%A, %B %d")
        md = [f"# Morning Brief — {date_str}", ""]
        if agenda_is_demo:
            md.append(
                "> ⚠ Agenda below is **demo data** — connect Google Workspace for your "
                "real calendar."
            )
            md.append("")
        md.append("## Agenda")
        if agenda_events:
            for e in agenda_events[:8]:
                md.append(
                    f"- **{e.get('start', '')[:16].replace('T', ' ')}** — "
                    f"{e.get('title', 'Untitled')}"
                    + (" *(demo)*" if agenda_is_demo or e.get("demo") else "")
                )
        else:
            md.append("_Nothing scheduled._")
        md += ["", "## Commitments due"]
        if due_soon:
            for c in due_soon[:8]:
                due = c.due_at.strftime("%a %H:%M") if c.due_at else "no date"
                md.append(f"- {c.title} — due {due}")
        else:
            md.append("_Nothing due in the next 48 hours._")
        md += ["", "## Needs your approval"]
        md.append(
            f"{len(pending_approvals)} pending approval(s) in the queue."
            if pending_approvals
            else "_Approval queue is clear._"
        )
        md += ["", "## Projects"]
        md.append(
            f"{len(projects)} active project(s). Recent note changes:"
            if changed_notes
            else f"{len(projects)} active project(s); no note edits in the last 2 days."
        )
        for ch in changed_notes:
            md.append(f"- `{ch['rel_path']}` ({ch['modified'][:16].replace('T', ' ')})")

        data = {
            "date": date_str,
            "agenda": agenda_events,
            "agenda_is_demo": agenda_is_demo,
            "commitments_due": [c.title for c in due_soon],
            "pending_approvals": len(pending_approvals),
            "active_projects": len(projects),
            "recent_changes": changed_notes,
        }
        return SkillResult(
            summary_md=(
                f"{len(agenda_events)} agenda items{' (demo)' if agenda_is_demo else ''}, "
                f"{len(due_soon)} commitments due, {len(pending_approvals)} approvals pending."
            ),
            data=data,
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title=f"Morning Brief — {date_str}",
                    filename="morning-brief.md",
                    content="\n".join(md),
                ),
                ArtifactSpec(
                    kind="json",
                    title="Morning Brief data",
                    filename="morning-brief.json",
                    content=json.dumps(data, indent=2, ensure_ascii=False, default=str),
                    mime="application/json",
                ),
            ],
            sources=(
                [{"label": "Demo calendar", "reference": "data/demo/agenda.json"}]
                if agenda_is_demo
                else []
            )
            + [
                {"label": f"Note: {c['rel_path']}", "reference": c["rel_path"]}
                for c in changed_notes
            ],
        )
