"""Weekly Review — wins, commitments, slippage, decisions, lessons from local records."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from cockpit.models import Artifact, Commitment, Memory, Run
from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillResult


class WeeklyReviewExecutor(BaseSkillExecutor):
    slug = "weekly-review"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "Collect the week's runs, artifacts, and commitments",
                "Summarize wins, slippage, and decisions",
                "Draft next week's focus",
            ],
            expected_tools=["obsidian.recent_changes"],
            side_effects_expected=False,
            success_checks=["Review artifact exists"],
        )

    async def execute(self) -> SkillResult:
        run = self.ctx.run
        week_ago = datetime.now(UTC) - timedelta(days=7)

        runs = (
            await self.ctx.session.scalars(
                select(Run).where(
                    Run.workspace_id == run.workspace_id,
                    Run.created_at >= week_ago,
                    Run.id != run.id,
                )
            )
        ).all()
        artifacts = (
            await self.ctx.session.scalars(
                select(Artifact).where(
                    Artifact.workspace_id == run.workspace_id, Artifact.created_at >= week_ago
                )
            )
        ).all()
        commitments = (
            await self.ctx.session.scalars(
                select(Commitment).where(Commitment.workspace_id == run.workspace_id)
            )
        ).all()
        decisions = (
            await self.ctx.session.scalars(
                select(Memory).where(
                    Memory.workspace_id == run.workspace_id,
                    Memory.kind == "decision",
                    Memory.created_at >= week_ago,
                )
            )
        ).all()
        changes = await self.ctx.call_tool(
            "obsidian.recent_changes",
            {"days": 7},
            purpose="Reviewing this week's note activity",
        )
        changed = changes.data.get("changed", []) if changes.ok else []

        done = [c for c in commitments if c.status == "done"]
        slipped = [
            c
            for c in commitments
            if c.status == "open" and c.due_at and c.due_at < datetime.now(UTC)
        ]
        completed_runs = [r for r in runs if r.status == "completed"]
        failed_runs = [r for r in runs if r.status == "failed"]

        now = datetime.now(UTC).strftime("%Y-%m-%d")
        md = [
            f"# Weekly Review — week ending {now}",
            "",
            "## Wins",
            f"- {len(done)} commitment(s) completed"
            if done
            else "- _No commitments marked done this week._",
            *[f"  - {c.title}" for c in done[:6]],
            f"- {len(completed_runs)} cockpit run(s) completed, "
            f"{len(artifacts)} artifact(s) produced",
            "",
            "## Slippage",
            *(
                [
                    f"- {c.title} (was due {c.due_at.strftime('%b %d') if c.due_at else '?'})"
                    for c in slipped[:8]
                ]
                or ["- _Nothing overdue. Clean week._"]
            ),
            "",
            "## Decisions recorded",
            *(
                [f"- {d.content[:120]}" for d in decisions[:6]]
                or [
                    "- _No decisions recorded — consider running Decision Memo when choices "
                    "come up._"
                ]
            ),
            "",
            "## Activity",
            f"- Notes touched: {len(changed)} · Runs: {len(runs)} ({len(failed_runs)} failed)",
            "",
            "## Next week's focus (proposal)",
            *(self._focus(slipped, changed)),
        ]

        data = {
            "week_ending": now,
            "wins": [c.title for c in done],
            "slipped": [c.title for c in slipped],
            "decisions": [d.content for d in decisions],
            "runs": len(runs),
            "artifacts": len(artifacts),
            "notes_touched": len(changed),
        }
        return SkillResult(
            summary_md=f"Week ending {now}: {len(done)} done, {len(slipped)} slipped, "
            f"{len(decisions)} decisions, {len(runs)} runs.",
            data=data,
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title=f"Weekly Review — {now}",
                    filename="weekly-review.md",
                    content="\n".join(md),
                ),
                ArtifactSpec(
                    kind="json",
                    title="Weekly Review data",
                    filename="weekly-review.json",
                    content=json.dumps(data, indent=2, ensure_ascii=False, default=str),
                    mime="application/json",
                ),
            ],
            sources=[
                {"label": "Cockpit run history", "reference": "runs (last 7 days)"},
                {"label": "Vault changes", "reference": "obsidian.recent_changes(7d)"},
            ],
        )

    def _focus(self, slipped: list, changed: list) -> list[str]:
        out = []
        if slipped:
            out.append(f"- Clear the {len(slipped)} overdue commitment(s) first.")
        if not changed:
            out.append("- The vault was quiet — schedule one writing/thinking block.")
        out.append("- Pick one project for a decisive push; park the rest explicitly.")
        return out
