"""Skill executors. Definitions (manifests/schemas/prompts) live in <repo>/skills/<id>/."""

from cockpit.skills.base import BaseSkillExecutor, SkillContext, SkillFailure, SkillResult
from cockpit.skills.business_idea_triage import BusinessIdeaTriageExecutor
from cockpit.skills.commitment_sweep import CommitmentSweepExecutor
from cockpit.skills.daily_plan import DailyPlanExecutor
from cockpit.skills.decision_memo import DecisionMemoExecutor
from cockpit.skills.morning_brief import MorningBriefExecutor
from cockpit.skills.project_pulse import ProjectPulseExecutor
from cockpit.skills.research_run import ResearchRunExecutor
from cockpit.skills.weekly_review import WeeklyReviewExecutor

EXECUTORS: dict[str, type[BaseSkillExecutor]] = {
    "project-pulse": ProjectPulseExecutor,
    "decision-memo": DecisionMemoExecutor,
    "business-idea-triage": BusinessIdeaTriageExecutor,
    "morning-brief": MorningBriefExecutor,
    "daily-plan": DailyPlanExecutor,
    "weekly-review": WeeklyReviewExecutor,
    "commitment-sweep": CommitmentSweepExecutor,
    "research-run": ResearchRunExecutor,
}

__all__ = [
    "EXECUTORS",
    "BaseSkillExecutor",
    "SkillContext",
    "SkillFailure",
    "SkillResult",
]
