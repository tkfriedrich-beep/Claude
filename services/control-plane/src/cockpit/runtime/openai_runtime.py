"""OpenAIAgentRuntime — adapter over the OpenAI Chat Completions API (API-key auth).

Design constraints (BUILD_BRIEF + architecture invariants):
- Authentication is an API key held in the SecretStore (``OPENAI_API_KEY``), never in the DB.
- The runtime is a text-only reasoning engine: it exposes no tools to the model, so a turn can
  produce words but never an external effect. Tool use stays with skills/connectors behind the
  policy gateway.
- Everything OpenAI-specific stays in this module; only normalized RuntimeEvents leave it.
- ``available()`` reports honestly (no key / no SDK-equivalent) instead of raising at import.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

from cockpit.enums import EventType
from cockpit.logging import get_logger
from cockpit.runtime.base import (
    PermissionCallback,
    ProviderUnavailable,
    RuntimeEvent,
    SessionContext,
)
from cockpit.runtime.http_chat import HTTPChatRuntime, usage_from_tokens
from cockpit.secrets import get_secret_store

log = get_logger("cockpit.runtime.openai")

API_KEY_NAME = "OPENAI_API_KEY"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Curated selector list. Users may also type any model id the account can access.
KNOWN_MODELS: list[str] = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4.1-nano",
    "o4-mini",
]

# Approximate USD per 1M tokens (input, output). Token counts from the API are authoritative;
# cost is a best-effort estimate and 0 for unknown models. Matched by longest-prefix.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
}


def _base_url() -> str:
    return (os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


class OpenAIAgentRuntime(HTTPChatRuntime):
    provider_id = "openai"
    default_model = "gpt-4o-mini"

    def available(self) -> tuple[bool, str]:
        if not get_secret_store().exists(API_KEY_NAME):
            return False, (
                "No OpenAI API key set. Add OPENAI_API_KEY in Integrations → Secrets "
                "(or export it in your shell) to enable OpenAI."
            )
        return True, f"OpenAI ready (auth via {API_KEY_NAME}, model {self.default_model} default)."

    async def stream_events(  # type: ignore[override]
        self, ctx: SessionContext, can_use_tool: PermissionCallback | None = None
    ) -> AsyncIterator[RuntimeEvent]:
        api_key = get_secret_store().get(API_KEY_NAME)
        if not api_key:
            raise ProviderUnavailable(
                "OpenAI API key disappeared before the request. Re-add it in "
                "Integrations → Secrets."
            )
        user_text = self._take_pending(ctx)
        model = self.resolve_model(ctx)
        messages = self._messages_for_turn(ctx, user_text)

        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=15.0)

        parts: list[str] = []
        tokens_in = tokens_out = 0
        stop_reason = "end_turn"
        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream(
                    "POST", f"{_base_url()}/chat/completions", json=body, headers=headers
                ) as response,
            ):
                if response.status_code != 200:
                    raw = (await response.aread()).decode("utf-8", "replace")
                    raise ProviderUnavailable(_explain_error(response.status_code, raw))
                async for line in response.aiter_lines():
                    if self._is_interrupted(ctx):
                        stop_reason = "interrupted"
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices", []):
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            parts.append(piece)
                            yield RuntimeEvent(EventType.ASSISTANT_MESSAGE_DELTA, {"text": piece})
                        if choice.get("finish_reason"):
                            stop_reason = _map_finish(choice["finish_reason"])
                    if chunk.get("usage"):
                        tokens_in = int(chunk["usage"].get("prompt_tokens", 0) or 0)
                        tokens_out = int(chunk["usage"].get("completion_tokens", 0) or 0)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"Could not reach OpenAI ({exc}). Check your network and API key."
            ) from exc

        reply = "".join(parts)
        self._record_reply(ctx, reply)
        yield RuntimeEvent(
            EventType.RUN_COMPLETED,
            {
                "stop_reason": stop_reason,
                "usage": usage_from_tokens(model, tokens_in, tokens_out, PRICES),
                "model": model,
            },
        )


def _map_finish(reason: str) -> str:
    return {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}.get(
        reason, reason
    )


def _explain_error(status: int, raw: str) -> str:
    detail = raw
    try:
        parsed = json.loads(raw)
        detail = (parsed.get("error") or {}).get("message") or raw
    except json.JSONDecodeError:
        pass
    detail = detail[:300]
    if status in (401, 403):
        return f"OpenAI rejected the API key ({status}): {detail}"
    if status == 404:
        return f"OpenAI model not found ({status}): {detail}"
    if status == 429:
        return f"OpenAI rate limit / quota ({status}): {detail}"
    return f"OpenAI request failed ({status}): {detail}"


async def list_models() -> list[str]:
    """Models the configured key can access, best-effort; falls back to the curated list."""
    api_key = get_secret_store().get(API_KEY_NAME)
    if not api_key:
        return list(KNOWN_MODELS)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(
                f"{_base_url()}/models", headers={"Authorization": f"Bearer {api_key}"}
            )
        if response.status_code != 200:
            return list(KNOWN_MODELS)
        ids = [m.get("id", "") for m in response.json().get("data", [])]
        chat = sorted(i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")))
        return chat or list(KNOWN_MODELS)
    except httpx.HTTPError:
        return list(KNOWN_MODELS)
