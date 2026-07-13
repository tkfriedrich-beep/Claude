"""Shared plumbing for stateless HTTP chat providers (OpenAI, Ollama).

Both are request/response chat APIs with no server-side session, so the control plane keeps a
short in-memory transcript per internal session and replays it each turn. Subclasses implement
``available()``, model resolution, and the provider-specific streaming request; everything else
(session lifecycle, history, interrupt) lives here so the two runtimes stay tiny and identical
where it matters.

Scope note (MVP): these runtimes are text-only reasoning engines — they do not expose tools to
the provider, so no external effect can originate from a model turn. Tool use stays with skills
and connectors behind the policy gateway. The ``can_use_tool`` bridge is accepted for interface
parity and simply goes unused here.
"""

from __future__ import annotations

from typing import Any

from cockpit.ids import new_id
from cockpit.runtime.base import AgentRuntime, SessionContext, Usage


class HTTPChatRuntime(AgentRuntime):
    provider_id = "http-chat"
    default_model = ""

    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, str]]] = {}
        self._pending: dict[str, str] = {}
        self._interrupted: set[str] = set()

    # ---- model ------------------------------------------------------------
    def resolve_model(self, ctx: SessionContext) -> str:
        model = str(ctx.settings.get("model") or "").strip()
        return model or self.default_model

    # ---- session lifecycle -------------------------------------------------
    def _seed(self, ctx: SessionContext) -> list[dict[str, str]]:
        return self._history.setdefault(
            ctx.internal_session_id,
            [{"role": "system", "content": ctx.system_prompt}],
        )

    async def start_session(self, ctx: SessionContext) -> None:
        if not ctx.external_session_id:
            ctx.external_session_id = new_id(self.provider_id)
        # Fresh transcript, seeded with the system prompt.
        self._history[ctx.internal_session_id] = [{"role": "system", "content": ctx.system_prompt}]

    async def resume_session(self, ctx: SessionContext) -> None:
        # No server-side session to reattach to; rebuild a local transcript if this process
        # doesn't have one (e.g. after a restart). Prior turns aren't replayed — honest about
        # what survives, rather than pretending to remember.
        if ctx.internal_session_id not in self._history:
            await self.start_session(ctx)

    async def send_input(self, ctx: SessionContext, text: str) -> None:
        self._seed(ctx)
        self._pending[ctx.internal_session_id] = text
        self._interrupted.discard(ctx.internal_session_id)

    async def interrupt(self, ctx: SessionContext) -> None:
        self._interrupted.add(ctx.internal_session_id)

    async def cancel(self, ctx: SessionContext) -> None:
        self._interrupted.add(ctx.internal_session_id)

    async def get_usage(self, ctx: SessionContext) -> Usage:
        return Usage()  # usage is reported per-turn on RUN_COMPLETED; aggregated by the worker

    async def close_session(self, ctx: SessionContext) -> None:
        self._history.pop(ctx.internal_session_id, None)
        self._pending.pop(ctx.internal_session_id, None)
        self._interrupted.discard(ctx.internal_session_id)

    # ---- helpers for subclasses -------------------------------------------
    def _take_pending(self, ctx: SessionContext) -> str:
        return self._pending.pop(ctx.internal_session_id, "")

    def _messages_for_turn(self, ctx: SessionContext, user_text: str) -> list[dict[str, str]]:
        history = self._seed(ctx)
        history.append({"role": "user", "content": user_text})
        return list(history)

    def _record_reply(self, ctx: SessionContext, text: str) -> None:
        if text:
            self._seed(ctx).append({"role": "assistant", "content": text})

    def _is_interrupted(self, ctx: SessionContext) -> bool:
        return ctx.internal_session_id in self._interrupted


def price_for(model: str, table: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """(input, output) USD per 1M tokens for `model`, matched by the longest key prefix.

    Best-effort only: token counts come from the provider and are authoritative; cost is a
    convenience estimate and is 0.0 for models not in the table (e.g. local Ollama models).
    """
    best: tuple[float, float] | None = None
    best_len = -1
    for key, price in table.items():
        if model.startswith(key) and len(key) > best_len:
            best, best_len = price, len(key)
    return best or (0.0, 0.0)


def usage_from_tokens(
    model: str, tokens_in: int, tokens_out: int, table: dict[str, tuple[float, float]]
) -> dict[str, Any]:
    price_in, price_out = price_for(model, table)
    cost = (tokens_in / 1_000_000) * price_in + (tokens_out / 1_000_000) * price_out
    return {
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "cost_usd": round(cost, 6),
    }
