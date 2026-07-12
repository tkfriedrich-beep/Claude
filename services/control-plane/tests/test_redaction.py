"""Secrets never reach logs or persisted events (THREAT_MODEL invariant)."""

from __future__ import annotations

from cockpit.logging import MASK, redact, redact_text


def test_sensitive_keys_masked_recursively() -> None:
    data = {
        "api_key": "super-secret-value",
        "nested": {"Authorization": "Bearer abcdef1234567890abcdef", "ok": "fine"},
        "list": [{"password": "hunter2"}],
    }
    clean = redact(data)
    assert clean["api_key"] == MASK
    assert clean["nested"]["Authorization"] == MASK
    assert clean["list"][0]["password"] == MASK
    assert clean["nested"]["ok"] == "fine"


def test_credential_shaped_values_masked_in_plain_strings() -> None:
    text = "calling with sk-ant-api03-verylongsecretkeyvalue123 and ghp_" + "a" * 30
    clean = redact_text(text)
    assert "sk-ant" not in clean
    assert "ghp_" not in clean
    assert MASK in clean


def test_normal_content_untouched() -> None:
    data = {"title": "Write scorecard", "path": "/ideas/x.md", "count": 3}
    assert redact(data) == data


async def test_events_persist_redacted_payloads(workspace: dict) -> None:
    from sqlalchemy import select

    from cockpit.db import db_session
    from cockpit.enums import EventType
    from cockpit.events import get_bus
    from cockpit.ids import new_id
    from cockpit.models import Run, RunEvent

    async with db_session() as session:
        run = Run(id=new_id("run"), workspace_id=workspace["workspace_id"], status="queued")
        session.add(run)
        await session.flush()
        await get_bus().emit(
            session,
            workspace_id=run.workspace_id,
            run_id=run.id,
            type=EventType.TOOL_PROGRESS,
            payload={"message": "ok", "api_key": "leaky-secret", "token": "xoxb-123456789012-abc"},
        )
        await session.commit()
        event = await session.scalar(select(RunEvent).where(RunEvent.run_id == run.id))
        assert event.payload["api_key"] == MASK
        assert event.payload["token"] == MASK
        assert event.payload["message"] == "ok"
