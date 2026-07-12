"""Project Pulse — scan project notes; report movement, risks, blocked items, next actions."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillFailure, SkillResult

CHECKBOX_OPEN = re.compile(r"^\s*[-*] \[ \] (.+)$", re.MULTILINE)
CHECKBOX_DONE = re.compile(r"^\s*[-*] \[[xX]\] (.+)$", re.MULTILINE)
BLOCKED_RE = re.compile(r"\b(blocked|blocker|waiting on|stuck)\b[:\s]*(.*)", re.IGNORECASE)
NEXT_RE = re.compile(
    r"^\s*(?:next|next action|next step)s?\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE
)
STALE_DAYS = 10


class ProjectPulseExecutor(BaseSkillExecutor):
    slug = "project-pulse"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "List project notes in the vault (/projects)",
                "Read each project note",
                "Detect movement, blocked items, risks, and next actions",
                "Compose a source-linked pulse report",
            ],
            expected_tools=["obsidian.list_notes", "obsidian.read_note", "obsidian.recent_changes"],
            side_effects_expected=False,
            success_checks=["Report artifact exists", "Every project links its source note"],
        )

    async def execute(self) -> SkillResult:
        listing = await self.ctx.call_tool(
            "obsidian.list_notes",
            {"section": "projects"},
            purpose="Reading your project notes",
        )
        if not listing.ok:
            raise SkillFailure(f"Could not list project notes: {listing.error}")
        notes = listing.data.get("notes", [])
        if not notes:
            raise SkillFailure("No project notes found under /projects in the configured vault.")

        recent = await self.ctx.call_tool(
            "obsidian.recent_changes",
            {"days": 7, "section": "projects"},
            purpose="Checking which projects moved this week",
        )
        recently_changed = (
            {c["rel_path"] for c in recent.data.get("changed", [])} if recent.ok else set()
        )

        projects: list[dict[str, Any]] = []
        for note in notes[:15]:
            await self.ctx.progress(f"Analyzing {note['title']}…")
            read = await self.ctx.call_tool(
                "obsidian.read_note",
                {"path": note["rel_path"]},
                purpose=f"Reading project note “{note['title']}”",
            )
            if not read.ok:
                continue
            content = read.data.get("content", "")
            fm = read.data.get("frontmatter", {})
            open_tasks = CHECKBOX_OPEN.findall(content)
            done_tasks = CHECKBOX_DONE.findall(content)
            blocked = [m[1].strip() or m[0] for m in BLOCKED_RE.findall(content)][:5]
            next_actions = NEXT_RE.findall(content)[:5] or open_tasks[:3]
            modified = datetime.fromisoformat(note["modified"])
            age_days = (datetime.now(UTC) - modified).days
            risks: list[str] = []
            if age_days >= STALE_DAYS:
                risks.append(f"No edits in {age_days} days — possibly stalled")
            if blocked:
                risks.append("Has blocked items")
            if not next_actions:
                risks.append("No clear next action recorded")
            projects.append(
                {
                    "name": fm.get("title") or note["title"],
                    "status": fm.get("status", "unknown"),
                    "source": note["rel_path"],
                    "moved_this_week": note["rel_path"] in recently_changed,
                    "age_days": age_days,
                    "open_tasks": len(open_tasks),
                    "done_tasks": len(done_tasks),
                    "blocked_items": blocked,
                    "next_actions": [n.strip() for n in next_actions],
                    "risks": risks,
                }
            )

        projects.sort(key=lambda p: (not p["moved_this_week"], -p["open_tasks"]))
        moved = [p for p in projects if p["moved_this_week"]]
        stalled = [p for p in projects if p["age_days"] >= STALE_DAYS]
        blocked_projects = [p for p in projects if p["blocked_items"]]

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "# Project Pulse",
            f"*Generated {now} · {len(projects)} projects scanned from your vault*",
            "",
            f"**Movement this week:** {len(moved)} of {len(projects)} projects changed. "
            f"**Blocked:** {len(blocked_projects)}. **Possibly stalled:** {len(stalled)}.",
            "",
        ]
        for p in projects:
            badge = (
                "🟢 moved"
                if p["moved_this_week"]
                else ("🟠 stalled" if p["age_days"] >= STALE_DAYS else "⚪ quiet")
            )
            lines += [
                f"## {p['name']}  ·  {badge}",
                f"- Status: `{p['status']}` · {p['open_tasks']} open / {p['done_tasks']} done "
                f"tasks · last edit {p['age_days']}d ago",
            ]
            if p["blocked_items"]:
                lines.append("- **Blocked:** " + "; ".join(p["blocked_items"]))
            if p["next_actions"]:
                lines.append("- **Next:** " + "; ".join(p["next_actions"][:3]))
            if p["risks"]:
                lines.append("- Risks: " + "; ".join(p["risks"]))
            lines.append(f"- Source: `{p['source']}`")
            lines.append("")

        summary = (
            f"Scanned {len(projects)} projects: {len(moved)} moved this week, "
            f"{len(blocked_projects)} blocked, {len(stalled)} possibly stalled."
        )
        return SkillResult(
            summary_md=summary,
            data={"projects": projects, "generated_at": now},
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title="Project Pulse report",
                    filename="project-pulse.md",
                    content="\n".join(lines),
                ),
                ArtifactSpec(
                    kind="json",
                    title="Project Pulse data",
                    filename="project-pulse.json",
                    content=_json({"projects": projects}),
                    mime="application/json",
                ),
            ],
            sources=[{"label": p["name"], "reference": p["source"]} for p in projects],
            unresolved=[
                f"{p['name']}: blocked — {'; '.join(p['blocked_items'])}" for p in blocked_projects
            ],
        )


def _json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, indent=2, ensure_ascii=False, default=str)
