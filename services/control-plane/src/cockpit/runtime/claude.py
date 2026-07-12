"""ClaudeAgentRuntime — adapter over the official Claude Agent SDK.

Design constraints (BUILD_BRIEF + ADR-011):
- The core is built on the SDK's typed session client, not on scraping terminal output.
- Chat sessions get read-only built-in tools (Read/Glob/Grep) pinned to configured roots via
  the can_use_tool permission callback; writes are not exposed to the provider at all.
- Provider session ids are persisted separately (provider_sessions.external_session_id) and
  used for resume.
- All SDK objects stay inside this module; everything leaving is a normalized RuntimeEvent.

The SDK is an optional dependency: available() reports honestly instead of raising at import.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from cockpit.enums import EventType
from cockpit.logging import get_logger
from cockpit.runtime.base import (
    AgentRuntime,
    PermissionCallback,
    ProviderUnavailable,
    RuntimeEvent,
    SessionContext,
    Usage,
)

log = get_logger("cockpit.runtime.claude")

PROMPT_DIR = Path(__file__).parent / "prompts"
READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]


def load_otto_prompt(version: str, *, assistant_name: str, user_name: str) -> str:
    path = PROMPT_DIR / f"{version}.md"
    if not path.exists():
        path = PROMPT_DIR / "otto_v1.md"
    template = path.read_text(encoding="utf-8")
    return template.replace("{assistant_name}", assistant_name).replace("{user_name}", user_name)


def _sdk():
    try:
        import claude_agent_sdk

        return claude_agent_sdk
    except ImportError as exc:
        raise ProviderUnavailable(
            "claude-agent-sdk is not installed. Install with: uv sync --extra claude"
        ) from exc


def _path_within(candidate: str, roots: list[Path]) -> bool:
    try:
        resolved = Path(candidate).expanduser().resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


class ClaudeAgentRuntime(AgentRuntime):
    provider_id = "claude"

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def available(self) -> tuple[bool, str]:
        try:
            _sdk()
        except ProviderUnavailable as exc:
            return False, str(exc)
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_cli = shutil.which("claude") is not None
        if not has_key and not has_cli:
            return False, (
                "No ANTHROPIC_API_KEY set and no authenticated `claude` CLI found. "
                "Configure one of them to enable the Claude runtime."
            )
        via = "ANTHROPIC_API_KEY" if has_key else "the local `claude` CLI"
        return True, f"Claude Agent SDK ready (auth via {via})."

    def _options(
        self, ctx: SessionContext, *, resume: str | None, can_use_tool: PermissionCallback | None
    ) -> Any:
        sdk = _sdk()
        roots = ctx.workspace_roots

        async def permission_callback(
            tool_name: str, tool_input: dict[str, Any], _context: Any = None
        ) -> Any:
            allowed, reason, updated = await self._check_permission(
                tool_name, tool_input, roots, can_use_tool
            )
            if allowed:
                return sdk.PermissionResultAllow(updated_input=updated or None)
            return sdk.PermissionResultDeny(message=reason)

        kwargs: dict[str, Any] = {
            "system_prompt": ctx.system_prompt,
            "allowed_tools": READ_ONLY_TOOLS,
            "max_turns": int(ctx.settings.get("max_turns", 8)),
            "cwd": str(roots[0]) if roots else None,
            "can_use_tool": permission_callback,
            # Do not inherit filesystem settings/CLAUDE.md — the cockpit owns configuration.
            "setting_sources": [],
        }
        if resume:
            kwargs["resume"] = resume
        try:
            return sdk.ClaudeAgentOptions(**kwargs)
        except TypeError:
            # Older/newer SDKs may not know some kwargs; drop optional ones and retry.
            kwargs.pop("setting_sources", None)
            return sdk.ClaudeAgentOptions(**kwargs)

    async def _check_permission(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        roots: list[Path],
        can_use_tool: PermissionCallback | None,
    ) -> tuple[bool, str, dict[str, Any]]:
        # Read-only built-ins: allow only inside configured roots.
        if tool_name in READ_ONLY_TOOLS:
            path = str(tool_input.get("file_path") or tool_input.get("path") or "")
            if not path:
                pattern_path = str(tool_input.get("cwd") or (roots[0] if roots else ""))
                path = pattern_path
            if path and _path_within(path, roots):
                return True, "", tool_input
            return (
                False,
                (
                    "That path is outside the roots this cockpit allows "
                    f"({', '.join(str(r) for r in roots)})."
                ),
                tool_input,
            )
        # Anything else is not exposed in the MVP (ADR-011); the external callback may
        # still choose to route specific requests through the approval gateway.
        if can_use_tool is not None:
            return await can_use_tool(tool_name, tool_input)
        return False, "This tool is not enabled for cockpit chat sessions.", tool_input

    async def start_session(self, ctx: SessionContext) -> None:
        await self._connect(ctx, resume=None)

    async def resume_session(self, ctx: SessionContext) -> None:
        await self._connect(ctx, resume=ctx.external_session_id)

    async def _connect(self, ctx: SessionContext, *, resume: str | None) -> None:
        sdk = _sdk()
        ok, detail = self.available()
        if not ok:
            raise ProviderUnavailable(detail)
        options = self._options(ctx, resume=resume, can_use_tool=self._pending_callback(ctx))
        client = sdk.ClaudeSDKClient(options=options)
        try:
            await client.connect()
        except Exception as exc:
            raise ProviderUnavailable(f"Could not start Claude session: {exc}") from exc
        self._clients[ctx.internal_session_id] = client

    # can_use_tool must be wired before connect(); stream_events swaps in the live callback.
    def _pending_callback(self, ctx: SessionContext) -> PermissionCallback | None:
        holder = self._callbacks = getattr(self, "_callbacks", {})

        async def dispatch(
            tool_name: str, tool_input: dict[str, Any]
        ) -> tuple[bool, str, dict[str, Any]]:
            cb = holder.get(ctx.internal_session_id)
            if cb is None:
                return False, "No permission handler attached.", tool_input
            return await cb(tool_name, tool_input)

        return dispatch

    async def send_input(self, ctx: SessionContext, text: str) -> None:
        client = self._clients.get(ctx.internal_session_id)
        if client is None:
            raise ProviderUnavailable("Session not connected.")
        await client.query(text)

    async def stream_events(  # type: ignore[override]
        self, ctx: SessionContext, can_use_tool: PermissionCallback | None = None
    ) -> AsyncIterator[RuntimeEvent]:
        sdk = _sdk()
        client = self._clients.get(ctx.internal_session_id)
        if client is None:
            raise ProviderUnavailable("Session not connected.")
        getattr(self, "_callbacks", {})[ctx.internal_session_id] = can_use_tool

        async for message in client.receive_response():
            # init system message carries the provider session id
            if isinstance(message, sdk.SystemMessage):
                session_id = (getattr(message, "data", None) or {}).get("session_id")
                if session_id:
                    ctx.external_session_id = str(session_id)
                continue
            if isinstance(message, sdk.AssistantMessage):
                for block in message.content:
                    if isinstance(block, sdk.TextBlock):
                        yield RuntimeEvent(EventType.ASSISTANT_MESSAGE_DELTA, {"text": block.text})
                    elif isinstance(block, sdk.ToolUseBlock):
                        yield RuntimeEvent(
                            EventType.TOOL_STARTED,
                            {
                                "tool_id": f"claude.{block.name}",
                                "provider_tool": block.name,
                                "purpose": _describe_builtin(block.name, block.input),
                            },
                        )
                continue
            if isinstance(message, sdk.UserMessage):
                for block in message.content if isinstance(message.content, list) else []:
                    if isinstance(block, sdk.ToolResultBlock):
                        yield RuntimeEvent(
                            EventType.TOOL_COMPLETED,
                            {
                                "tool_id": "claude.builtin",
                                "summary": "Finished reading",
                                "is_error": bool(getattr(block, "is_error", False)),
                            },
                        )
                continue
            if isinstance(message, sdk.ResultMessage):
                if getattr(message, "session_id", None):
                    ctx.external_session_id = str(message.session_id)
                usage = getattr(message, "usage", None) or {}
                yield RuntimeEvent(
                    EventType.RUN_COMPLETED,
                    {
                        "stop_reason": getattr(message, "subtype", "end_turn"),
                        "is_error": bool(getattr(message, "is_error", False)),
                        "usage": {
                            "tokens_in": int(usage.get("input_tokens", 0) or 0),
                            "tokens_out": int(usage.get("output_tokens", 0) or 0),
                            "cost_usd": float(getattr(message, "total_cost_usd", 0.0) or 0.0),
                        },
                        "num_turns": getattr(message, "num_turns", None),
                        "duration_ms": getattr(message, "duration_ms", None),
                    },
                )
                return

    async def interrupt(self, ctx: SessionContext) -> None:
        client = self._clients.get(ctx.internal_session_id)
        if client is not None:
            await client.interrupt()

    async def cancel(self, ctx: SessionContext) -> None:
        await self.close_session(ctx)

    async def get_usage(self, ctx: SessionContext) -> Usage:
        return Usage()  # usage arrives per-turn on ResultMessage; aggregated by the worker

    async def close_session(self, ctx: SessionContext) -> None:
        client = self._clients.pop(ctx.internal_session_id, None)
        getattr(self, "_callbacks", {}).pop(ctx.internal_session_id, None)
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # already gone is fine
                log.info("claude client disconnect raised; ignoring")


async def one_shot(prompt: str, *, system_prompt: str, timeout_seconds: int = 120) -> str:
    """Stateless single-turn generation with no tools — used for skill text enrichment."""
    import asyncio

    sdk = _sdk()
    options = sdk.ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=[],
        max_turns=1,
        setting_sources=[],
    )

    async def _run() -> str:
        parts: list[str] = []
        async for message in sdk.query(prompt=prompt, options=options):
            if isinstance(message, sdk.AssistantMessage):
                for block in message.content:
                    if isinstance(block, sdk.TextBlock):
                        parts.append(block.text)
        return "".join(parts)

    return await asyncio.wait_for(_run(), timeout=timeout_seconds)


def _describe_builtin(name: str, tool_input: dict[str, Any]) -> str:
    target = tool_input.get("file_path") or tool_input.get("pattern") or ""
    labels = {"Read": "Reading", "Glob": "Finding files", "Grep": "Searching"}
    verb = labels.get(name, f"Using {name}")
    return f"{verb} {target}".strip()
