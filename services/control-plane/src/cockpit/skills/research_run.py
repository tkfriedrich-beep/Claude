"""Research Run — source-backed memo. Provider-dependent; honest about evidence limits.

Without a healthy provider this fails cleanly at planning time. With a provider but no web
connector, the memo is knowledge-based and says so explicitly — facts/inferences/unknowns are
separated and the missing-browsing limitation is stated in the artifact (BUILD_BRIEF: external
browsing is connector/provider dependent).
"""

from __future__ import annotations

from datetime import UTC, datetime

from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillFailure, SkillResult


class ResearchRunExecutor(BaseSkillExecutor):
    slug = "research-run"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "Frame the research question",
                "Generate a structured memo via the provider",
                "Separate facts, inferences, and unknowns",
            ],
            expected_tools=[],
            side_effects_expected=False,
            success_checks=["Memo artifact exists", "Evidence limits stated"],
            assumption="No web-browsing connector is configured; the memo will be "
            "knowledge-based and labeled as such.",
        )

    async def execute(self) -> SkillResult:
        question = (self.ctx.input.get("question") or self.ctx.run.command_text or "").strip()
        if not question:
            raise SkillFailure("A research question is required (input field `question`).")

        prompt = (
            "Write a research memo on the question below. Structure strictly as:\n"
            "## Facts (only what you are confident about; note recency limits)\n"
            "## Inferences (label each with what it rests on)\n"
            "## Unknowns (what would need live sources to answer)\n"
            "## Recommended next sources\n"
            "You have NO web access — say so where it matters. Max 500 words.\n\n"
            f"Question: {question}"
        )
        body = await self.ctx.generate(prompt)
        if body is None:
            raise SkillFailure(
                "Research Run needs a healthy model provider (connect Claude in "
                "Integrations). No provider is available, and no web connector is configured."
            )

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        md = [
            f"# Research memo: {question}",
            f"*Generated {now} · knowledge-based (no web connector configured) · "
            "verify time-sensitive claims*",
            "",
            body.strip(),
        ]
        return SkillResult(
            summary_md=f"Research memo drafted for: {question[:80]} "
            "(knowledge-based — no live sources).",
            data={"question": question, "mode": "knowledge_based"},
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title=f"Research — {question[:60]}",
                    filename="research-memo.md",
                    content="\n".join(md),
                    meta={"generation_mode": "llm_assisted"},
                )
            ],
            sources=[{"label": "Model knowledge (no live browsing)", "reference": "provider"}],
            unresolved=["No web connector configured — live sources unavailable."],
            generation_mode="llm_assisted",
        )
