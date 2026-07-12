"""Run finite-state machine — the only writer of run.status.

Transitions emit normalized events. Invalid transitions raise InvalidTransition and are
unit-tested (BUILD_BRIEF §Data model).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.enums import TERMINAL_STATUSES, EventType, RunStatus
from cockpit.events import EventBus
from cockpit.models import Run

VALID_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.TRIAGING, RunStatus.CANCELLED},
    RunStatus.TRIAGING: {
        RunStatus.PLANNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.PLANNING: {
        RunStatus.AWAITING_APPROVAL,
        RunStatus.EXECUTING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.AWAITING_APPROVAL: {
        RunStatus.EXECUTING,
        RunStatus.QUEUED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.EXECUTING: {
        RunStatus.VERIFYING,
        RunStatus.AWAITING_APPROVAL,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INTERRUPTED,
    },
    RunStatus.VERIFYING: {RunStatus.REVIEWING, RunStatus.FAILED, RunStatus.INTERRUPTED},
    RunStatus.REVIEWING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED},
    RunStatus.INTERRUPTED: {RunStatus.QUEUED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}

_TERMINAL_EVENTS = {
    RunStatus.COMPLETED: EventType.RUN_COMPLETED,
    RunStatus.FAILED: EventType.RUN_FAILED,
    RunStatus.CANCELLED: EventType.RUN_CANCELLED,
}


class InvalidTransition(Exception):
    def __init__(self, run_id: str, frm: str, to: str) -> None:
        super().__init__(f"run {run_id}: invalid transition {frm} → {to}")
        self.frm, self.to = frm, to


def can_transition(frm: RunStatus | str, to: RunStatus | str) -> bool:
    return RunStatus(to) in VALID_TRANSITIONS[RunStatus(frm)]


async def transition(
    session: AsyncSession,
    bus: EventBus,
    run: Run,
    to: RunStatus,
    *,
    reason: str | None = None,
) -> Run:
    frm = RunStatus(run.status)
    if to not in VALID_TRANSITIONS[frm]:
        raise InvalidTransition(run.id, frm.value, to.value)

    now = datetime.now(UTC)
    run.status = to.value
    run.status_reason = reason
    if to is RunStatus.QUEUED:
        # Re-queued (resume / approval continuation): drop any stale claim so a worker can
        # pick it up again — the claim guard keys off worker_claim being NULL (review F3).
        run.worker_claim = None
    if frm is RunStatus.QUEUED and to is RunStatus.TRIAGING:
        run.started_at = run.started_at or now
    if to in TERMINAL_STATUSES:
        run.finished_at = now
    if to is RunStatus.FAILED and reason:
        run.error = reason

    if frm is RunStatus.QUEUED and to is RunStatus.TRIAGING:
        await bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.RUN_STARTED,
            payload={"from": frm.value, "to": to.value},
        )
    await bus.emit(
        session,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type=EventType.AGENT_STATUS_CHANGED,
        payload={"from": frm.value, "to": to.value, **({"reason": reason} if reason else {})},
    )
    if to in _TERMINAL_EVENTS:
        await bus.emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=_TERMINAL_EVENTS[to],
            payload={"reason": reason} if reason else {},
        )
    await session.flush()
    return run
