"""AgentRuntime — the provider-neutral interface (BUILD_BRIEF §Model and agent runtime).

The control plane owns sessions, events, approvals, and usage; a runtime only translates
between one provider's session model and these calls. Provider events must be normalized —
nothing provider-specific may leak past this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cockpit.enums import EventType


class ProviderUnavailable(Exception):
    """Provider not installed / not authenticated / unreachable."""


@dataclass
class RuntimeEvent:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    human_text: str | None = None


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    final_text: str
    usage: Usage = field(default_factory=Usage)
    external_session_id: str | None = None
    stop_reason: str = "end_turn"


@dataclass
class SessionContext:
    workspace_id: str
    internal_session_id: str
    external_session_id: str | None
    system_prompt: str
    workspace_roots: list[Path]
    assistant_name: str = "Otto"
    settings: dict[str, Any] = field(default_factory=dict)


# Called when the provider wants to use a tool. Returns (allowed, reason, updated_input).
# Implementations bridge this to the approval gateway — never auto-answer writes.
PermissionCallback = Callable[[str, dict[str, Any]], Awaitable[tuple[bool, str, dict[str, Any]]]]


class AgentRuntime(ABC):
    provider_id: str = "base"

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """(is_available, human detail). Must never raise."""

    @abstractmethod
    async def start_session(self, ctx: SessionContext) -> None: ...

    @abstractmethod
    async def resume_session(self, ctx: SessionContext) -> None:
        """Attach to ctx.external_session_id where the provider supports it."""

    @abstractmethod
    async def send_input(self, ctx: SessionContext, text: str) -> None: ...

    @abstractmethod
    def stream_events(
        self, ctx: SessionContext, can_use_tool: PermissionCallback | None = None
    ) -> AsyncIterator[RuntimeEvent]:
        """Yield normalized events for the current turn until the turn completes."""

    @abstractmethod
    async def interrupt(self, ctx: SessionContext) -> None: ...

    @abstractmethod
    async def cancel(self, ctx: SessionContext) -> None: ...

    @abstractmethod
    async def get_usage(self, ctx: SessionContext) -> Usage: ...

    @abstractmethod
    async def close_session(self, ctx: SessionContext) -> None: ...

    async def run_turn(
        self,
        ctx: SessionContext,
        text: str,
        on_event: Callable[[RuntimeEvent], Awaitable[None]],
        can_use_tool: PermissionCallback | None = None,
    ) -> TurnResult:
        """Convenience driver: send input, forward streamed events, return the result."""
        await self.send_input(ctx, text)
        final_text_parts: list[str] = []
        usage = Usage()
        stop_reason = "end_turn"
        async for event in self.stream_events(ctx, can_use_tool):
            if event.type is EventType.ASSISTANT_MESSAGE_DELTA:
                final_text_parts.append(str(event.payload.get("text", "")))
            if event.type is EventType.RUN_COMPLETED:
                usage = Usage(
                    **{
                        k: v
                        for k, v in event.payload.get("usage", {}).items()
                        if k in ("tokens_in", "tokens_out", "cost_usd")
                    }
                )
                stop_reason = event.payload.get("stop_reason", "end_turn")
                continue  # synthetic terminal marker — not re-emitted
            await on_event(event)
        return TurnResult(
            final_text="".join(final_text_parts),
            usage=usage,
            external_session_id=ctx.external_session_id,
            stop_reason=stop_reason,
        )
