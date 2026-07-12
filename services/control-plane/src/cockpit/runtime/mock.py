"""MockAgentRuntime — deterministic scripted runtime for demo mode and tests.

Honest by design: it never claims external effects. Replies are clearly labeled as coming from
the offline demo runtime. Saying "try a file read" exercises the permission callback path.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from cockpit.enums import EventType
from cockpit.ids import new_id
from cockpit.runtime.base import (
    AgentRuntime,
    PermissionCallback,
    RuntimeEvent,
    SessionContext,
    Usage,
)


class MockAgentRuntime(AgentRuntime):
    provider_id = "mock"

    def __init__(self, delay: float = 0.02) -> None:
        self._delay = delay
        self._pending: dict[str, str] = {}
        self._interrupted: set[str] = set()

    def available(self) -> tuple[bool, str]:
        return True, "Deterministic offline runtime (demo mode)."

    async def start_session(self, ctx: SessionContext) -> None:
        ctx.external_session_id = new_id("mock")

    async def resume_session(self, ctx: SessionContext) -> None:
        if not ctx.external_session_id:
            await self.start_session(ctx)

    async def send_input(self, ctx: SessionContext, text: str) -> None:
        self._pending[ctx.internal_session_id] = text
        self._interrupted.discard(ctx.internal_session_id)

    async def interrupt(self, ctx: SessionContext) -> None:
        self._interrupted.add(ctx.internal_session_id)

    async def cancel(self, ctx: SessionContext) -> None:
        self._interrupted.add(ctx.internal_session_id)

    async def get_usage(self, ctx: SessionContext) -> Usage:
        return Usage()

    async def close_session(self, ctx: SessionContext) -> None:
        self._pending.pop(ctx.internal_session_id, None)

    async def stream_events(  # type: ignore[override]
        self, ctx: SessionContext, can_use_tool: PermissionCallback | None = None
    ) -> AsyncIterator[RuntimeEvent]:
        text = self._pending.pop(ctx.internal_session_id, "")
        lower = text.lower()

        async def say(message: str) -> AsyncIterator[RuntimeEvent]:
            for chunk in _chunks(message, 48):
                if ctx.internal_session_id in self._interrupted:
                    yield RuntimeEvent(
                        EventType.RUN_COMPLETED,
                        {"stop_reason": "interrupted", "usage": {}},
                    )
                    return
                await asyncio.sleep(self._delay)
                yield RuntimeEvent(EventType.ASSISTANT_MESSAGE_DELTA, {"text": chunk})

        reply = self._reply_for(lower, ctx)

        if "read" in lower and can_use_tool is not None:
            # Exercise the permission bridge with a benign read proposal.
            allowed, reason, _ = await can_use_tool("local_files.list", {"glob": "**/*.md"})
            note = (
                "I listed your local Markdown files through the tool gateway."
                if allowed
                else f"The file listing was not permitted ({reason}), so I stopped there."
            )
            reply = f"{note}\n\n{reply}"

        async for event in say(reply):
            yield event
            if event.type is EventType.RUN_COMPLETED:
                return
        yield RuntimeEvent(
            EventType.RUN_COMPLETED,
            {
                "stop_reason": "end_turn",
                "usage": {
                    "tokens_in": len(text) // 4,
                    "tokens_out": len(reply) // 4,
                    "cost_usd": 0.0,
                },
            },
        )

    def _reply_for(self, lower: str, ctx: SessionContext) -> str:
        name = ctx.assistant_name
        if self.provider_id == "mock" and not lower.strip():
            return f"({name}, offline demo runtime) I didn't receive any text."
        if "hello" in lower or "hi" in lower or "hey" in lower:
            return (
                f"Hello — I'm {name}, running on the offline demo runtime right now. "
                "I can't reach any model provider, but the cockpit around me is fully live: "
                "try running the Project Pulse skill, or connect Claude in Integrations to "
                "give me a real reasoning engine."
            )
        if "what can you do" in lower or "help" in lower:
            return (
                "Right now I'm the deterministic demo runtime, so I answer honestly but "
                "simply. The skills, approvals, and history around me are real. Connect a "
                "provider (Integrations → Claude) for open-ended reasoning."
            )
        return (
            f"({name}, offline demo runtime) I registered your request: “{lower[:140]}”. "
            "A real model provider isn't connected, so I won't pretend to answer it. "
            "The fastest useful path: run a skill (they work fully offline on your local "
            "data), or connect Claude in Integrations."
        )


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]
