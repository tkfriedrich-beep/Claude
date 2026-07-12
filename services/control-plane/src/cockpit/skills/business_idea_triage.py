"""Business Idea Triage — score ideas in the configured folder; write-backs need approval.

Source files are never altered without approval: scorecard write-backs go through
local_files.write (approval: required). In draft/shadow mode the write becomes a dry-run diff
preview. A denied write is recorded as skipped — the triage itself still completes.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cockpit.gateway import ToolDenied
from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillFailure, SkillResult

SIGNALS: dict[str, list[str]] = {
    "problem_clarity": ["problem", "pain", "struggle", "frustrat", "need"],
    "market": ["market", "customer", "audience", "segment", "tam", "niche"],
    "monetization": ["revenue", "price", "pricing", "subscription", "charge", "monetiz", "pay"],
    "moat": ["moat", "defensib", "unique", "advantage", "network effect", "proprietary"],
    "validation": [
        "interview",
        "waitlist",
        "signup",
        "pilot",
        "prototype",
        "landing page",
        "pre-order",
        "validat",
    ],
}


class BusinessIdeaTriageExecutor(BaseSkillExecutor):
    slug = "business-idea-triage"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "List idea files in your configured ideas folder",
                "Read and score each idea (problem, market, monetization, moat, validation)",
                "Draft a scorecard and the next validation action per idea",
                "Propose writing scorecards back next to the ideas (requires your approval)",
            ],
            expected_tools=["local_files.list", "local_files.read", "local_files.write"],
            side_effects_expected=True,
            success_checks=["Scorecard artifact exists", "Source files unchanged unless approved"],
            assumption="Ideas are Markdown/text files; one idea per file.",
        )

    def _ideas_root(self) -> str:
        root = self.ctx.ws.bizideas_path or (
            str(self.ctx.settings.demo_dir / "bizideas") if self.ctx.demo_mode else None
        )
        if not root:
            raise SkillFailure(
                "No ideas folder configured — set one in Settings → Storage (or enable demo data)."
            )
        return root

    async def execute(self) -> SkillResult:
        root = self._ideas_root()
        listing = await self.ctx.call_tool(
            "local_files.list",
            {"root": root, "glob": "*.md"},
            purpose="Listing your business idea files",
        )
        entries = [
            e for e in listing.data.get("entries", []) if not e["path"].endswith(".scorecard.md")
        ]
        txt = await self.ctx.call_tool(
            "local_files.list",
            {"root": root, "glob": "*.txt"},
            purpose="Listing idea text files",
        )
        entries += txt.data.get("entries", [])
        if not entries:
            raise SkillFailure(f"No idea files (*.md, *.txt) found in {root}.")

        ideas: list[dict[str, Any]] = []
        for entry in entries[:12]:
            name = Path(entry["path"]).stem
            await self.ctx.progress(f"Scoring “{name}”…")
            read = await self.ctx.call_tool(
                "local_files.read",
                {"path": entry["path"]},
                purpose=f"Reading idea “{name}”",
            )
            if not read.ok:
                continue
            content = read.data.get("content", "")
            scores = self._score(content)
            total = round(sum(scores.values()) / len(scores), 1)
            ideas.append(
                {
                    "name": _title_from(content) or name.replace("-", " ").title(),
                    "file": entry["path"],
                    "scores": scores,
                    "total": total,
                    "verdict": "pursue"
                    if total >= 3.5
                    else ("explore" if total >= 2.3 else "park"),
                    "next_validation_action": self._next_action(scores),
                    "word_count": len(content.split()),
                }
            )

        ideas.sort(key=lambda i: -i["total"])
        writebacks: list[dict[str, str]] = []
        for idea in ideas:
            scorecard = self._scorecard_md(idea)
            target = str(Path(idea["file"]).with_suffix("")) + ".scorecard.md"
            try:
                write = await self.ctx.call_tool(
                    "local_files.write",
                    {"path": target, "content": scorecard},
                    purpose=f"Write scorecard for “{idea['name']}” next to the idea file",
                    why="Keeps the evaluation with the idea so future you sees it in context.",
                )
                writebacks.append(
                    {
                        "idea": idea["name"],
                        "path": target,
                        "status": "written" if write.data.get("written") else "previewed (dry run)",
                    }
                )
            except ToolDenied as exc:
                writebacks.append(
                    {"idea": idea["name"], "path": target, "status": f"skipped — {exc.reason}"}
                )

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        md = [
            "# Business Idea Triage",
            f"*Generated {now} · {len(ideas)} ideas from `{root}`*",
            "",
            "| Idea | Problem | Market | Monetization | Moat | Validation | Total | Verdict |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i in ideas:
            s = i["scores"]
            md.append(
                f"| {i['name']} | {s['problem_clarity']} | {s['market']} | {s['monetization']} "
                f"| {s['moat']} | {s['validation']} | **{i['total']}** | {i['verdict']} |"
            )
        md.append("")
        for i in ideas:
            md += [
                f"## {i['name']} — {i['total']}/5 ({i['verdict']})",
                f"- Next validation action: **{i['next_validation_action']}**",
                f"- Source: `{i['file']}` ({i['word_count']} words)",
                "",
            ]
        md += ["## Scorecard write-backs", ""]
        md += [f"- {w['idea']}: {w['status']}" for w in writebacks]

        top = ideas[0] if ideas else None
        return SkillResult(
            summary_md=(
                f"Triaged {len(ideas)} ideas. Top: **{top['name']}** ({top['total']}/5, "
                f"{top['verdict']}). Next action: {top['next_validation_action']}"
                if top
                else "No ideas found."
            ),
            data={"ideas": ideas, "writebacks": writebacks, "root": root},
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title="Idea triage scorecards",
                    filename="idea-triage.md",
                    content="\n".join(md),
                ),
                ArtifactSpec(
                    kind="json",
                    title="Idea triage data",
                    filename="idea-triage.json",
                    content=json.dumps(
                        {"ideas": ideas, "writebacks": writebacks}, indent=2, ensure_ascii=False
                    ),
                    mime="application/json",
                ),
            ],
            sources=[{"label": i["name"], "reference": i["file"]} for i in ideas],
            unresolved=[
                w["idea"] + ": scorecard " + w["status"]
                for w in writebacks
                if w["status"].startswith("skipped")
            ],
        )

    def _score(self, content: str) -> dict[str, int]:
        lower = content.lower()
        scores: dict[str, int] = {}
        for dimension, keywords in SIGNALS.items():
            hits = sum(lower.count(k) for k in keywords)
            # 1 = absent, 5 = discussed repeatedly. Heuristic, honestly labeled in SKILL.md.
            scores[dimension] = max(1, min(5, 1 + hits))
        return scores

    def _next_action(self, scores: dict[str, int]) -> str:
        weakest = min(scores, key=lambda k: scores[k])
        actions = {
            "problem_clarity": "Write the problem statement in one sentence and find 3 people "
            "who have it this week.",
            "market": "Size the reachable market: who exactly buys this, and where do 100 of "
            "them gather?",
            "monetization": "Draft one price point and test willingness to pay in 5 conversations.",
            "moat": "Write down why this stays defensible after the first copycat appears.",
            "validation": "Run the cheapest possible test: a landing page or 5 problem interviews.",
        }
        return actions[weakest]

    def _scorecard_md(self, idea: dict[str, Any]) -> str:
        s = idea["scores"]
        return "\n".join(
            [
                f"# Scorecard: {idea['name']}",
                "",
                "*Generated by AgenticOS Cockpit — Business Idea Triage (heuristic scoring)*",
                "",
                f"- Problem clarity: {s['problem_clarity']}/5",
                f"- Market: {s['market']}/5",
                f"- Monetization: {s['monetization']}/5",
                f"- Moat: {s['moat']}/5",
                f"- Validation: {s['validation']}/5",
                f"- **Total: {idea['total']}/5 — {idea['verdict']}**",
                "",
                f"**Next validation action:** {idea['next_validation_action']}",
                "",
                f"Source idea: `{idea['file']}`",
            ]
        )


def _title_from(content: str) -> str | None:
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None
