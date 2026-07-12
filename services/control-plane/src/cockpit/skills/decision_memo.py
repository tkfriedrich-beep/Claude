"""Decision Memo — Judgment-OS structure with Markdown + JSON artifacts.

Deterministic-first (ADR-007): the memo is composed from the user's structured input; when a
provider is healthy, ctx.generate() adds an analysis section and the artifact is labeled
llm_assisted. The memo never invents evidence — absent input stays visibly absent.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from cockpit.skills.base import ArtifactSpec, BaseSkillExecutor, Plan, SkillFailure, SkillResult


class DecisionMemoExecutor(BaseSkillExecutor):
    slug = "decision-memo"

    async def plan(self) -> Plan:
        return Plan(
            steps=[
                "Structure the decision, context, and options",
                "Weigh options against stated evidence and assumptions",
                "Write recommendation, pre-mortem, and review date",
                "Export Markdown and JSON artifacts",
            ],
            expected_tools=[],
            side_effects_expected=False,
            success_checks=["Markdown artifact exists", "JSON validates against output schema"],
        )

    async def execute(self) -> SkillResult:
        inp = self.ctx.input
        decision = (inp.get("decision") or "").strip()
        if not decision:
            raise SkillFailure("A decision statement is required (input field `decision`).")
        options: list[dict[str, Any]] = [
            o if isinstance(o, dict) else {"name": str(o)} for o in inp.get("options", [])
        ]
        if len(options) < 2:
            raise SkillFailure("At least two options are required to write a decision memo.")
        context = (inp.get("context") or "").strip()
        criteria: list[str] = [str(c) for c in inp.get("criteria", [])]
        deadline = inp.get("deadline")

        generation_mode = "deterministic"
        analysis: str | None = None
        prompt = self._analysis_prompt(decision, context, options, criteria)
        generated = await self.ctx.generate(prompt)
        if generated:
            analysis = generated.strip()
            generation_mode = "llm_assisted"

        scored = self._score_options(options, criteria)
        recommendation = scored[0]
        confidence = "medium" if analysis else "low"
        review_date = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        md = [
            f"# Decision memo: {decision}",
            f"*Generated {now} · mode: {generation_mode}*",
            "",
            "## Decision",
            decision,
            "",
            "## Context",
            context or "_No context provided — add it to strengthen this memo._",
            "",
            "## Options",
        ]
        for opt in scored:
            md.append(f"### {opt['name']}")
            if opt.get("notes"):
                md.append(str(opt["notes"]))
            md.append(f"- Evidence provided: {opt.get('evidence') or '_none stated_'}")
            md.append(f"- Trade-offs: {opt.get('tradeoffs') or '_none stated_'}")
            md.append("")
        md += [
            "## Evidence & assumptions",
            "**Stated evidence:** "
            + (
                "; ".join(filter(None, (str(o.get("evidence") or "") for o in options)))
                or "_none provided — this memo rests on judgment, not data._"
            ),
            "**Assumptions:** "
            + (
                "; ".join(str(a) for a in inp.get("assumptions", [])) or "_none stated explicitly._"
            ),
            "",
            "## Criteria",
            (
                "\n".join(f"- {c}" for c in criteria)
                if criteria
                else "_No explicit criteria given; ranking uses stated evidence density only._"
            ),
            "",
        ]
        if analysis:
            md += ["## Analysis (Otto)", analysis, ""]
        md += [
            "## Recommendation",
            f"**{recommendation['name']}** — {recommendation['why']}",
            f"Confidence: **{confidence}**"
            + (
                " (no model provider connected — structure only, no independent analysis)"
                if not analysis
                else ""
            ),
            "",
            "## Pre-mortem",
            f"If this fails in 6 months, the most likely causes: "
            f"{self._premortem(recommendation, inp)}",
            "",
            "## Review",
            f"Revisit this decision by **{review_date}**"
            + (f" (stated deadline: {deadline})" if deadline else "")
            + ".",
        ]

        result_json = {
            "decision": decision,
            "context": context,
            "options": scored,
            "criteria": criteria,
            "recommendation": recommendation["name"],
            "recommendation_rationale": recommendation["why"],
            "confidence": confidence,
            "review_date": review_date,
            "generation_mode": generation_mode,
        }
        return SkillResult(
            summary_md=f"Recommendation: **{recommendation['name']}** ({confidence} confidence). "
            f"Review by {review_date}.",
            data=result_json,
            artifacts=[
                ArtifactSpec(
                    kind="markdown",
                    title=f"Decision memo — {decision[:60]}",
                    filename="decision-memo.md",
                    content="\n".join(md),
                    meta={"generation_mode": generation_mode},
                ),
                ArtifactSpec(
                    kind="json",
                    title="Decision memo (structured)",
                    filename="decision-memo.json",
                    content=json.dumps(result_json, indent=2, ensure_ascii=False),
                    mime="application/json",
                    meta={"generation_mode": generation_mode},
                ),
            ],
            sources=[{"label": "User-provided decision input", "reference": "command input"}],
            unresolved=[] if criteria else ["No explicit decision criteria were provided."],
            generation_mode=generation_mode,
        )

    def _score_options(
        self, options: list[dict[str, Any]], criteria: list[str]
    ) -> list[dict[str, Any]]:
        scored = []
        for opt in options:
            evidence = str(opt.get("evidence") or "")
            notes = str(opt.get("notes") or "")
            score = len(evidence) * 2 + len(notes)
            why = (
                "strongest stated evidence among the options"
                if evidence
                else "ranked by the detail provided; no evidence was stated"
            )
            scored.append({**opt, "why": why, "_score": score})
        scored.sort(key=lambda o: -o["_score"])
        for o in scored:
            o.pop("_score", None)
        return scored

    def _premortem(self, recommendation: dict[str, Any], inp: dict[str, Any]) -> str:
        risks = inp.get("risks") or []
        if risks:
            return "; ".join(str(r) for r in risks)
        return (
            "the assumptions above prove wrong, the unstated evidence gap "
            f"(“{recommendation.get('why', '')}”), or execution capacity falls short. "
            "List concrete risks in the input to sharpen this."
        )

    def _analysis_prompt(
        self, decision: str, context: str, options: list[dict[str, Any]], criteria: list[str]
    ) -> str:
        return (
            "Write a concise decision analysis (max 250 words) for this memo. Distinguish "
            "facts (only from the input), inferences, and recommendation. Flag uncertainty "
            "honestly.\n\n"
            f"Decision: {decision}\nContext: {context}\n"
            f"Options: {json.dumps(options, ensure_ascii=False)}\n"
            f"Criteria: {criteria}"
        )
