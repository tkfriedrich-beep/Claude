"""FSM: every valid transition works; invalid transitions raise; terminal states are final."""

from __future__ import annotations

import pytest

from cockpit.enums import TERMINAL_STATUSES, RunStatus
from cockpit.state_machine import VALID_TRANSITIONS, InvalidTransition, can_transition, transition


def test_transition_table_is_complete() -> None:
    assert set(VALID_TRANSITIONS) == set(RunStatus)


def test_terminal_states_have_no_exits() -> None:
    for status in TERMINAL_STATUSES:
        assert VALID_TRANSITIONS[status] == set()


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        (RunStatus.QUEUED, RunStatus.TRIAGING),
        (RunStatus.TRIAGING, RunStatus.PLANNING),
        (RunStatus.PLANNING, RunStatus.EXECUTING),
        (RunStatus.PLANNING, RunStatus.AWAITING_APPROVAL),
        (RunStatus.AWAITING_APPROVAL, RunStatus.QUEUED),
        (RunStatus.EXECUTING, RunStatus.VERIFYING),
        (RunStatus.EXECUTING, RunStatus.AWAITING_APPROVAL),
        (RunStatus.VERIFYING, RunStatus.REVIEWING),
        (RunStatus.REVIEWING, RunStatus.COMPLETED),
        (RunStatus.EXECUTING, RunStatus.INTERRUPTED),
        (RunStatus.INTERRUPTED, RunStatus.QUEUED),
    ],
)
def test_valid_transitions(frm: RunStatus, to: RunStatus) -> None:
    assert can_transition(frm, to)


@pytest.mark.parametrize(
    ("frm", "to"),
    [
        (RunStatus.COMPLETED, RunStatus.EXECUTING),
        (RunStatus.FAILED, RunStatus.QUEUED),
        (RunStatus.CANCELLED, RunStatus.TRIAGING),
        (RunStatus.QUEUED, RunStatus.EXECUTING),  # must triage/plan first
        (RunStatus.QUEUED, RunStatus.COMPLETED),
        (RunStatus.VERIFYING, RunStatus.EXECUTING),  # no going back
        (RunStatus.TRIAGING, RunStatus.COMPLETED),
    ],
)
def test_invalid_transitions(frm: RunStatus, to: RunStatus) -> None:
    assert not can_transition(frm, to)


async def test_transition_writes_status_and_events(workspace: dict) -> None:
    from sqlalchemy import select

    from cockpit.db import db_session
    from cockpit.events import get_bus
    from cockpit.ids import new_id
    from cockpit.models import Run, RunEvent

    async with db_session() as session:
        run = Run(id=new_id("run"), workspace_id=workspace["workspace_id"], status="queued")
        session.add(run)
        await session.flush()
        await transition(session, get_bus(), run, RunStatus.TRIAGING)
        with pytest.raises(InvalidTransition):
            await transition(session, get_bus(), run, RunStatus.COMPLETED)
        await session.commit()
        events = (
            await session.scalars(
                select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
            )
        ).all()
        assert [e.type for e in events] == ["run.started", "agent.status_changed"]
        assert run.status == "triaging"
        assert run.started_at is not None
