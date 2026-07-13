"""Runtime layer: mock streaming/interrupt; Claude adapter surface; provider stubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from cockpit.enums import EventType
from cockpit.runtime import ProviderUnavailable, get_runtime
from cockpit.runtime.base import SessionContext
from cockpit.runtime.claude import ClaudeAgentRuntime, load_otto_prompt
from cockpit.runtime.mock import MockAgentRuntime


def ctx(tmp_path: Path) -> SessionContext:
    return SessionContext(
        workspace_id="ws",
        internal_session_id="s1",
        external_session_id=None,
        system_prompt="test",
        workspace_roots=[tmp_path],
        assistant_name="Otto",
    )


async def test_mock_runtime_streams_and_completes(tmp_path: Path) -> None:
    runtime = MockAgentRuntime(delay=0)
    sctx = ctx(tmp_path)
    await runtime.start_session(sctx)
    assert sctx.external_session_id and sctx.external_session_id.startswith("mock_")
    events = []

    async def on_event(e):
        events.append(e)

    result = await runtime.run_turn(sctx, "hello", on_event)
    assert "Otto" in result.final_text
    assert any(e.type is EventType.ASSISTANT_MESSAGE_DELTA for e in events)
    assert result.stop_reason == "end_turn"


async def test_mock_runtime_interrupt_stops_stream(tmp_path: Path) -> None:
    runtime = MockAgentRuntime(delay=0)
    sctx = ctx(tmp_path)
    await runtime.start_session(sctx)
    await runtime.send_input(sctx, "hello hello hello")
    await runtime.interrupt(sctx)
    stops = []
    async for event in runtime.stream_events(sctx):
        if event.type is EventType.RUN_COMPLETED:
            stops.append(event.payload.get("stop_reason"))
    assert stops == ["interrupted"]


async def test_mock_permission_callback_denial_is_reported(tmp_path: Path) -> None:
    runtime = MockAgentRuntime(delay=0)
    sctx = ctx(tmp_path)
    await runtime.start_session(sctx)

    async def deny(tool, tool_input):
        return False, "policy said no", tool_input

    async def on_event(e):
        pass

    result = await runtime.run_turn(sctx, "please read my files", on_event, deny)
    assert "not permitted" in result.final_text


def test_claude_runtime_available_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ok, detail = ClaudeAgentRuntime().available()
    assert isinstance(ok, bool) and detail  # depends on env; must answer, not raise


async def test_claude_permission_check_denies_outside_roots(tmp_path: Path) -> None:
    runtime = ClaudeAgentRuntime()
    allowed, reason, _ = await runtime._check_permission(
        "Read", {"file_path": "/etc/passwd"}, [tmp_path], None
    )
    assert allowed is False and "outside the roots" in reason
    allowed_in, _reason, _input = await runtime._check_permission(
        "Read", {"file_path": str(tmp_path / "a.md")}, [tmp_path], None
    )
    assert allowed_in is True


async def test_claude_unknown_tool_denied_without_bridge(tmp_path: Path) -> None:
    runtime = ClaudeAgentRuntime()
    allowed, _reason, _ = await runtime._check_permission(
        "Bash", {"command": "rm -rf /"}, [tmp_path], None
    )
    assert allowed is False


def test_otto_prompt_versioned_and_personalized() -> None:
    prompt = load_otto_prompt("otto_v1", assistant_name="Nova", user_name="Kim")
    assert "Nova" in prompt and "Kim" in prompt
    assert "never claim" in prompt.lower() or "Never claim" in prompt


def test_stub_providers_refuse_honestly() -> None:
    # langgraph is still a scaffold; unknown providers are refused; both must not crash the app.
    with pytest.raises(ProviderUnavailable):
        get_runtime("langgraph")
    with pytest.raises(ProviderUnavailable):
        get_runtime("unknown-thing")


def test_openai_ollama_are_real_runtimes() -> None:
    from cockpit.runtime import OllamaAgentRuntime, OpenAIAgentRuntime

    assert isinstance(get_runtime("openai"), OpenAIAgentRuntime)
    assert isinstance(get_runtime("ollama"), OllamaAgentRuntime)
    # get_runtime is a singleton per provider — interrupt/cancel must reach the live instance.
    assert get_runtime("openai") is get_runtime("openai")


def test_openai_available_false_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from cockpit.runtime.openai_runtime import OpenAIAgentRuntime

    ok, detail = OpenAIAgentRuntime().available()
    assert ok is False and "OPENAI_API_KEY" in detail  # honest, never raises


def test_ollama_available_never_raises() -> None:
    from cockpit.runtime.ollama_runtime import OllamaAgentRuntime

    ok, detail = OllamaAgentRuntime().available()
    assert isinstance(ok, bool) and detail  # depends on whether a local daemon is up
