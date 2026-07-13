"""OllamaAgentRuntime — adapter over a local Ollama server (private, offline).

Design constraints:
- Talks to a local Ollama daemon (default http://localhost:11434); no cloud, no API key, no
  cost. Model tokens are reported when Ollama returns them; cost is always 0.
- Text-only reasoning engine (no tools exposed to the model) — same scope as the OpenAI runtime.
- ``available()`` probes reachability with a fast socket connect and never raises.
- Everything Ollama-specific stays here; only normalized RuntimeEvents leave.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx

from cockpit.enums import EventType
from cockpit.logging import get_logger
from cockpit.runtime.base import (
    PermissionCallback,
    ProviderUnavailable,
    RuntimeEvent,
    SessionContext,
)
from cockpit.runtime.http_chat import HTTPChatRuntime

log = get_logger("cockpit.runtime.ollama")

DEFAULT_HOST = "http://localhost:11434"


def _host() -> str:
    return (os.environ.get("COCKPIT_OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")


def _host_port() -> tuple[str, int]:
    parsed = urlparse(_host())
    return parsed.hostname or "localhost", parsed.port or 11434


class OllamaAgentRuntime(HTTPChatRuntime):
    provider_id = "ollama"
    default_model = ""  # no universal default; resolved from installed models at request time

    def available(self) -> tuple[bool, str]:
        host, port = _host_port()
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return True, f"Ollama reachable at {_host()}. Pick a local model."
        except OSError:
            return False, (
                f"No Ollama server at {_host()}. Install from https://ollama.com, run "
                "`ollama serve`, and `ollama pull llama3` to add a model."
            )

    async def stream_events(  # type: ignore[override]
        self, ctx: SessionContext, can_use_tool: PermissionCallback | None = None
    ) -> AsyncIterator[RuntimeEvent]:
        user_text = self._take_pending(ctx)
        model = self.resolve_model(ctx)
        if not model:
            installed = await list_models()
            if not installed:
                raise ProviderUnavailable(
                    "No Ollama models installed. Run `ollama pull llama3`, then pick it in "
                    "Integrations."
                )
            model = installed[0]

        messages = self._messages_for_turn(ctx, user_text)
        body = {"model": model, "messages": messages, "stream": True}
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=15.0, pool=10.0)

        parts: list[str] = []
        tokens_in = tokens_out = 0
        stop_reason = "end_turn"
        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream("POST", f"{_host()}/api/chat", json=body) as response,
            ):
                if response.status_code != 200:
                    raw = (await response.aread()).decode("utf-8", "replace")
                    raise ProviderUnavailable(_explain_error(response.status_code, raw, model))
                async for line in response.aiter_lines():
                    if self._is_interrupted(ctx):
                        stop_reason = "interrupted"
                        break
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise ProviderUnavailable(f"Ollama error: {str(chunk['error'])[:300]}")
                    piece = (chunk.get("message") or {}).get("content")
                    if piece:
                        parts.append(piece)
                        yield RuntimeEvent(EventType.ASSISTANT_MESSAGE_DELTA, {"text": piece})
                    if chunk.get("done"):
                        tokens_in = int(chunk.get("prompt_eval_count", 0) or 0)
                        tokens_out = int(chunk.get("eval_count", 0) or 0)
                        if chunk.get("done_reason") == "length":
                            stop_reason = "max_tokens"
                        break
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"Could not reach Ollama at {_host()} ({exc}). Is `ollama serve` running?"
            ) from exc

        reply = "".join(parts)
        self._record_reply(ctx, reply)
        yield RuntimeEvent(
            EventType.RUN_COMPLETED,
            {
                "stop_reason": stop_reason,
                "usage": {
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": 0.0,  # local inference is free
                },
                "model": model,
            },
        )


def _explain_error(status: int, raw: str, model: str) -> str:
    detail = raw
    try:
        detail = json.loads(raw).get("error", raw)
    except json.JSONDecodeError:
        pass
    detail = str(detail)[:300]
    if status == 404:
        return (
            f"Ollama model “{model}” not installed ({status}): run `ollama pull {model}`. {detail}"
        )
    return f"Ollama request failed ({status}): {detail}"


async def list_models() -> list[str]:
    """Installed model names via GET /api/tags. Empty list if Ollama is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            response = await client.get(f"{_host()}/api/tags")
        if response.status_code != 200:
            return []
        return sorted(m.get("name", "") for m in response.json().get("models", []) if m.get("name"))
    except httpx.HTTPError:
        return []
