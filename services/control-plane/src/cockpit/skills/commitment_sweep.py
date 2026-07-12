"""Commitment Sweep — find promises/follow-ups in notes; propose via the Memory Review queue.

Nothing is auto-committed: each detected promise becomes a MemoryProposal (status=proposed)
that the user approves, edits, or rejects in Memory Review (BUILD_BRIEF §memory).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from cockpit.skills.base import (
    ArtifactSpec,
    BaseSkillExecutor,
    MemoryProposal,
    Plan,
    SkillResult,
)

PATTERNS = [
    (
        re.compile(r"\bI(?:'ll| will| need to| promised to| should)\s+(.{8,120})", re.IGNORECASE),
        "first-person promise",
    ),
    (re.compile(r"\bfollow[- ]?up\b[:\s]*(.{4,120})", re.IGNORECASE), "follow-up marker"),
    (re.compile(r"^\s*[-*] \[ \] (.{4,140})$", re.MULTILINE), "open checkbox"),
    (re.compile(r"\bTODO\b[:\s]*(.{4,120})", re.IGNORECASE), "TODO marker"),
]
SEARCH_TERMS = ["I'll", "follow up", "TODO", "- [ ]"]


class CommitmentSweepExecutor(BaseSkillExecutor):
    slug = "commitment-sweep"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "Search notes for promises, follow-ups, and open TODOs",
                "Deduplicate and rank candidates",
                "Propose commitments for your review (nothing auto-saved)",
            ],
            expected_tools=["obsidian.search_notes", "obsidian.read_note"],
            side_effects_expected=False,
            success_checks=["Proposals go to Memory Review, not straight to commitments"],
        )

    async def execute(self) -> SkillResult:
        candidates: dict[str, dict[str, str]] = {}
        for term in SEARCH_TERMS:
            found = await self.ctx.call_tool(
                "obsidian.search_notes",
                {"query": term},
                purpose=f"Scanning notes for “{term}”",
            )
            if not found.ok:
                continue
            for match in found.data.get("matches", []):
                text = match["text"]
                for pattern, label in PATTERNS:
                    m = pattern.search(text)
                    if m:
                        commitment = m.group(1).strip().rstrip(".!,")
                        key = commitment.lower()[:80]
                        if key not in candidates:
                            candidates[key] = {
                                "commitment": commitment,
                                "kind": label,
                                "source": f"{match['rel_path']}:{match['line']}",
                                "excerpt": text[:200],
                            }
                        break

        found_list = list(candidates.values())[:20]
        proposals = [
            MemoryProposal(
                kind="commitment",
                content=c["commitment"],
                rationale=f"Detected a {c['kind']} in your notes — save it as a commitment "
                "so it doesn't get lost.",
                structured={"detected_as": c["kind"]},
                confidence=0.55,
                domain_key="today",
                sources=[
                    {"source_type": "file", "reference": c["source"], "excerpt": c["excerpt"]}
                ],
            )
            for c in found_list
        ]

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        md = [
            "# Commitment Sweep",
            f"*Generated {now} · {len(found_list)} candidate(s) found*",
            "",
            "These were **proposed to your Memory Review queue** — nothing is saved until "
            "you approve it.",
            "",
        ]
        for c in found_list:
            md += [f"- **{c['commitment']}**", f"  - {c['kind']} · source `{c['source']}`"]
        if not found_list:
            md.append("_No promises or open follow-ups detected in your notes._")

        return SkillResult(
            summary_md=f"Found {len(found_list)} commitment candidate(s); "
            "all sent to Memory Review for your approval.",
            data={"candidates": found_list},
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title="Commitment sweep results",
                    filename="commitment-sweep.md",
                    content="\n".join(md),
                ),
                ArtifactSpec(
                    kind="json",
                    title="Commitment sweep data",
                    filename="commitment-sweep.json",
                    content=json.dumps({"candidates": found_list}, indent=2, ensure_ascii=False),
                    mime="application/json",
                ),
            ],
            sources=[{"label": c["commitment"][:40], "reference": c["source"]} for c in found_list],
            memory_proposals=proposals,
        )
