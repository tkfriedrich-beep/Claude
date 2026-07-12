"""Scheduler — materializes due schedules into runs; sweeps expired approvals.

Shadow Mode (BUILD_BRIEF §Graduated autonomy): a shadow schedule's runs execute in draft
semantics — external effects become dry-run previews — so the user can see what *would* have
happened before granting real autonomy.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from cockpit.config import Settings
from cockpit.enums import ApprovalStatus, EventType, RunStatus
from cockpit.events import get_bus
from cockpit.ids import correlation_id, new_id
from cockpit.logging import get_logger
from cockpit.models import Approval, Run, Schedule
from cockpit.state_machine import transition

log = get_logger("cockpit.scheduler")


async def tick(settings: Settings) -> None:
    from cockpit.db import db_session

    bus = get_bus()
    now = datetime.now(UTC)
    async with db_session() as session:
        due = (
            await session.scalars(
                select(Schedule).where(
                    Schedule.enabled == True,  # noqa: E712
                    Schedule.next_run_at.is_not(None),
                    Schedule.next_run_at <= now,
                )
            )
        ).all()
        for schedule in due:
            run = Run(
                id=new_id("run"),
                workspace_id=schedule.workspace_id,
                kind="skill",
                status=RunStatus.QUEUED.value,
                title=f"{schedule.name} (scheduled{', shadow' if schedule.shadow_mode else ''})",
                skill_slug=schedule.skill_slug,
                schedule_id=schedule.id,
                command_text="",
                input=schedule.input or {},
                mode="draft"
                if schedule.shadow_mode
                else str((schedule.input or {}).get("mode", "draft")),
                shadow=schedule.shadow_mode,
                correlation_id=correlation_id(),
            )
            session.add(run)
            await session.flush()
            await bus.emit(
                session,
                workspace_id=run.workspace_id,
                run_id=run.id,
                type=EventType.RUN_QUEUED,
                payload={"scheduled": True, "shadow": schedule.shadow_mode},
            )
            schedule.last_run_at = now
            schedule.last_run_id = run.id
            schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
            log.info("schedule %s queued run %s", schedule.name, run.id, extra={"run_id": run.id})

        # keep last_run_status fresh
        for schedule in (await session.scalars(select(Schedule))).all():
            if schedule.last_run_id:
                last_run = await session.get(Run, schedule.last_run_id)
                if last_run is not None:
                    schedule.last_run_status = last_run.status

        # stale approval sweep — expired approvals cancel their waiting runs
        expired = (
            await session.scalars(
                select(Approval).where(
                    Approval.status == ApprovalStatus.PENDING.value,
                    Approval.expires_at.is_not(None),
                    Approval.expires_at < now,
                )
            )
        ).all()
        for approval in expired:
            approval.status = ApprovalStatus.EXPIRED.value
            approval.resolved_at = now
            waiting_run = await session.get(Run, approval.run_id)
            if (
                waiting_run is not None
                and RunStatus(waiting_run.status) is RunStatus.AWAITING_APPROVAL
            ):
                await bus.emit(
                    session,
                    workspace_id=run.workspace_id,
                    run_id=run.id,
                    type=EventType.APPROVAL_RESOLVED,
                    payload={
                        "approval_id": approval.id,
                        "decision": "expired",
                        "title": approval.title,
                    },
                )
                await transition(
                    session,
                    bus,
                    run,
                    RunStatus.CANCELLED,
                    reason="The pending approval expired before you resolved it.",
                )
        await session.commit()


async def scheduler_loop(settings: Settings, *, stop: asyncio.Event) -> None:
    log.info("scheduler started (poll %.0fs)", settings.scheduler_poll_seconds)
    while not stop.is_set():
        try:
            await tick(settings)
        except Exception:
            log.exception("scheduler tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.scheduler_poll_seconds)
        except TimeoutError:
            pass
    log.info("scheduler stopped")
