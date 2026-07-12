"""Skill executors run end-to-end through the real pipeline on demo fixtures."""

from __future__ import annotations

from sqlalchemy import select

from tests.conftest import get_run, submit_and_process


async def test_project_pulse_produces_sourced_report(workspace: dict) -> None:
    run_id = await submit_and_process(workspace["workspace_id"], skill_slug="project-pulse")
    run = await get_run(run_id)
    assert run.status == "completed", run.error
    assert run.verification and run.verification["passed"] is True
    projects = run.result["data"]["projects"]
    assert len(projects) == 3
    assert all(p["source"].endswith(".md") for p in projects)
    blocked = [p for p in projects if p["blocked_items"]]
    assert len(blocked) == 2  # website-relaunch + q3 pipeline carry "Blocked:" markers
    assert run.result["artifacts"], "artifacts recorded on result"


async def test_business_idea_triage_draft_mode_previews_writes(workspace: dict) -> None:
    run_id = await submit_and_process(
        workspace["workspace_id"], skill_slug="business-idea-triage", mode="draft"
    )
    run = await get_run(run_id)
    # draft mode: local_files.write has approval: required → run pauses for the human even
    # though the write itself is a local R2 (approval tightening from the manifest).
    assert run.status == "awaiting_approval"
    scorecards = list(workspace["ideas_dir"].glob("*.scorecard.md"))
    assert scorecards == [], "no writes before approval"


async def test_business_idea_triage_scores_and_ranks(workspace: dict) -> None:
    """Deny all write-backs → triage still completes with skips recorded."""
    from cockpit.db import db_session
    from cockpit.enums import ApprovalStatus, RunStatus, ToolCallStatus
    from cockpit.models import Approval, Run, ToolCall
    from cockpit.worker import process_run_inline

    run_id = await submit_and_process(
        workspace["workspace_id"], skill_slug="business-idea-triage", mode="draft"
    )
    for _ in range(4):  # up to 3 idea write-backs
        run = await get_run(run_id)
        if run.status != RunStatus.AWAITING_APPROVAL.value:
            break
        async with db_session() as session:
            approval = await session.scalar(
                select(Approval).where(
                    Approval.run_id == run_id, Approval.status == ApprovalStatus.PENDING.value
                )
            )
            approval.status = ApprovalStatus.DENIED.value
            call = await session.get(ToolCall, approval.tool_call_id)
            call.status = ToolCallStatus.DENIED.value
            call.error = "denied in test"
            db_run = await session.get(Run, run_id)
            db_run.status = RunStatus.QUEUED.value  # what the resolve endpoint does via FSM
            await session.commit()
        await process_run_inline(run_id)

    run = await get_run(run_id)
    assert run.status == "completed", run.error
    ideas = run.result["data"]["ideas"]
    assert len(ideas) == 3
    assert ideas[0]["total"] >= ideas[-1]["total"], "ranked by score"
    by_name = {i["name"]: i for i in ideas}
    assert by_name["Vault Concierge"]["total"] < by_name["Ops Audit Template Pack"]["total"]
    assert all(i["next_validation_action"] for i in ideas)
    assert len(run.result["unresolved"]) == 3  # all three write-backs skipped
    assert list(workspace["ideas_dir"].glob("*.scorecard.md")) == []


async def test_decision_memo_deterministic_artifacts(workspace: dict) -> None:
    run_id = await submit_and_process(
        workspace["workspace_id"],
        skill_slug="decision-memo",
        input={
            "decision": "Choose hosting for the relaunch",
            "context": "Static site, EU visitors, low budget",
            "options": [
                {"name": "Keep Netlify", "evidence": "zero migration cost, current setup works"},
                {"name": "Move to Vercel", "notes": "nicer previews"},
            ],
            "criteria": ["cost", "migration effort"],
        },
    )
    run = await get_run(run_id)
    assert run.status == "completed", run.error
    data = run.result["data"]
    assert data["recommendation"] == "Keep Netlify"  # option with stated evidence wins
    assert data["generation_mode"] == "deterministic"  # no provider in tests
    assert data["confidence"] == "low"  # honest: no analysis without a provider
    kinds = {a["kind"] for a in run.result["artifacts"]}
    assert kinds == {"markdown", "json"}


async def test_decision_memo_requires_two_options(workspace: dict) -> None:
    run_id = await submit_and_process(
        workspace["workspace_id"],
        skill_slug="decision-memo",
        input={"decision": "Pick a lane for the launch", "options": [{"name": "only one"}]},
    )
    run = await get_run(run_id)
    assert run.status == "failed"
    assert "too short" in (run.error or "") or "minItems" in (run.error or "")


async def test_commitment_sweep_proposes_memories_not_commitments(workspace: dict) -> None:
    from cockpit.db import db_session
    from cockpit.models import Commitment, Memory

    run_id = await submit_and_process(workspace["workspace_id"], skill_slug="commitment-sweep")
    run = await get_run(run_id)
    assert run.status == "completed", run.error
    assert run.result["data"]["candidates"], "demo vault contains promises/TODOs"
    async with db_session() as session:
        proposals = (
            await session.scalars(
                select(Memory).where(
                    Memory.workspace_id == workspace["workspace_id"], Memory.status == "proposed"
                )
            )
        ).all()
        commitments = (
            await session.scalars(
                select(Commitment).where(Commitment.workspace_id == workspace["workspace_id"])
            )
        ).all()
    assert proposals, "candidates land in the memory review queue"
    assert commitments == [], "nothing auto-committed without review"


async def test_morning_brief_labels_demo_agenda(workspace: dict) -> None:
    run_id = await submit_and_process(workspace["workspace_id"], skill_slug="morning-brief")
    run = await get_run(run_id)
    assert run.status == "completed", run.error
    assert run.result["data"]["agenda_is_demo"] is True
    md = [a for a in run.result["artifacts"] if a["kind"] == "markdown"]
    assert md, "brief artifact exists"


async def test_research_run_fails_cleanly_without_provider(workspace: dict) -> None:
    run_id = await submit_and_process(
        workspace["workspace_id"],
        skill_slug="research-run",
        input={"question": "What is the best CRM for solo consultants?"},
    )
    run = await get_run(run_id)
    assert run.status == "failed"
    assert "provider" in (run.error or "").lower()


async def test_chat_run_routes_to_mock_and_streams(workspace: dict) -> None:
    run_id = await submit_and_process(workspace["workspace_id"], kind="chat", text="hello there")
    run = await get_run(run_id)
    assert run.status == "completed"
    assert run.provider == "mock"
    assert "offline demo runtime" in run.result["summary_md"]

    from cockpit.db import db_session
    from cockpit.models import RunEvent

    async with db_session() as session:
        types = [
            e.type
            for e in (
                await session.scalars(
                    select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
                )
            ).all()
        ]
    assert "assistant.message_delta" in types
    assert types[-1] == "run.completed"


async def test_keyword_routing_selects_skill(workspace: dict) -> None:
    run_id = await submit_and_process(
        workspace["workspace_id"], kind="skill", text="give me a project pulse please"
    )
    run = await get_run(run_id)
    assert run.skill_slug == "project-pulse"
    assert run.status == "completed"
