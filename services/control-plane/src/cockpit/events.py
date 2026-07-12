"""Normalized event model: persistence-first, then in-process pub/sub.

The run_events table is the source of truth; the bus only accelerates delivery to open SSE
streams. Payloads are redacted before persistence. Every event carries human_text for the UI
timeline — raw payloads sit behind "Technical details".
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.enums import EventType
from cockpit.logging import get_logger, redact
from cockpit.models import RunEvent

log = get_logger("cockpit.events")


def humanize(event_type: EventType, payload: dict[str, Any]) -> str:
    """Human-readable line for the activity timeline. Calm, specific, no jargon."""
    p = payload
    match event_type:
        case EventType.RUN_QUEUED:
            return "Queued"
        case EventType.RUN_STARTED:
            return "Getting started"
        case EventType.AGENT_STATUS_CHANGED:
            labels = {
                "triaging": "Understanding the request",
                "planning": "Preparing a plan",
                "awaiting_approval": "Waiting for your approval",
                "executing": "Working on it",
                "verifying": "Checking the results",
                "reviewing": "Reviewing quality",
                "interrupted": "Paused",
                "queued": "Queued to continue",
            }
            return labels.get(str(p.get("to", "")), f"Status: {p.get('to', '?')}")
        case EventType.ASSISTANT_MESSAGE_DELTA:
            return ""  # deltas render as streaming text, not timeline lines
        case EventType.PLAN_CREATED:
            steps = p.get("steps") or []
            return f"Planned {len(steps)} step{'s' if len(steps) != 1 else ''}"
        case EventType.TOOL_PROPOSED:
            return p.get("purpose") or f"Proposing to use {p.get('tool_id', 'a tool')}"
        case EventType.APPROVAL_REQUIRED:
            return f"Waiting for approval: {p.get('title', 'a proposed action')}"
        case EventType.APPROVAL_RESOLVED:
            decision = p.get("decision", "resolved")
            return f"You {decision} “{p.get('title', 'the proposed action')}”"
        case EventType.TOOL_STARTED:
            return p.get("purpose") or f"Using {p.get('tool_id', 'a tool')}"
        case EventType.TOOL_PROGRESS:
            return str(p.get("message", "Working…"))
        case EventType.TOOL_COMPLETED:
            if p.get("dry_run"):
                return f"Previewed {p.get('tool_id', 'action')} (dry run — nothing changed)"
            return p.get("summary") or f"Finished {p.get('tool_id', 'a tool step')}"
        case EventType.TOOL_FAILED:
            return f"Step failed: {p.get('reason', p.get('tool_id', 'unknown'))}"
        case EventType.ARTIFACT_CREATED:
            return f"Created “{p.get('title', 'an artifact')}”"
        case EventType.VERIFICATION_COMPLETED:
            return (
                "Verified against expectations" if p.get("passed") else "Verification found issues"
            )
        case EventType.MEMORY_PROPOSED:
            return f"Proposed a memory for your review: {p.get('summary', '')}".strip()
        case EventType.RUN_COMPLETED:
            return "Done"
        case EventType.RUN_FAILED:
            return f"Failed: {p.get('reason', 'unknown error')}"
        case EventType.RUN_CANCELLED:
            return f"Cancelled{': ' + str(p['reason']) if p.get('reason') else ''}"
    return event_type.value


class EventBus:
    """In-process fan-out. Subscribers get dicts shaped like the SSE `data` payload."""

    def __init__(self) -> None:
        self._global: set[asyncio.Queue[dict[str, Any]]] = set()
        self._by_run: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._seq_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def subscribe(self, run_id: str | None = None) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        (self._by_run[run_id] if run_id else self._global).add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]], run_id: str | None = None) -> None:
        (self._by_run.get(run_id, set()) if run_id else self._global).discard(q)

    def _publish(self, data: dict[str, Any]) -> None:
        for q in list(self._global) + list(self._by_run.get(data["run_id"], set())):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:  # slow consumer: drop; SSE reconnect backfills from DB
                pass

    async def emit(
        self,
        session: AsyncSession,
        *,
        workspace_id: str,
        run_id: str,
        type: EventType,
        payload: dict[str, Any] | None = None,
        human_text: str | None = None,
    ) -> RunEvent:
        """Persist an event (redacted) and publish it. Caller owns the transaction."""
        clean: dict[str, Any] = redact(payload or {})
        async with self._seq_locks[run_id]:
            seq = (
                await session.scalar(
                    select(func.coalesce(func.max(RunEvent.seq), 0)).where(
                        RunEvent.run_id == run_id
                    )
                )
                or 0
            ) + 1
            event = RunEvent(
                workspace_id=workspace_id,
                run_id=run_id,
                seq=seq,
                type=type.value,
                ts=datetime.now(UTC),
                human_text=human_text if human_text is not None else humanize(type, clean),
                payload=clean,
            )
            session.add(event)
            await session.flush()  # assigns autoincrement id
        self._publish(event_to_dict(event))
        return event


def event_to_dict(e: RunEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "run_id": e.run_id,
        "seq": e.seq,
        "type": e.type,
        "ts": e.ts.isoformat() if e.ts else None,
        "human_text": e.human_text,
        "payload": e.payload,
    }


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
