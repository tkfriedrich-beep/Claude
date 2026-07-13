"""Provider runtimes (OpenAI/Ollama), the local SecretStore, and the providers/secrets APIs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from cockpit.enums import EventType
from cockpit.runtime.base import SessionContext
from cockpit.runtime.ollama_runtime import OllamaAgentRuntime
from cockpit.runtime.openai_runtime import OpenAIAgentRuntime
from cockpit.secrets import InvalidSecretName, LocalSecretStore, validate_secret_name


def _ctx(tmp_path: Path) -> SessionContext:
    return SessionContext(
        workspace_id="ws",
        internal_session_id="s1",
        external_session_id=None,
        system_prompt="You are Otto.",
        workspace_roots=[tmp_path],
        assistant_name="Otto",
        settings={"model": ""},
    )


# ----------------------------------------------------------------- secret store


def test_local_secret_store_roundtrip_and_perms(tmp_path: Path) -> None:
    store = LocalSecretStore(tmp_path / "secrets.env")
    assert store.get("OPENAI_API_KEY") is None
    assert store.list_names() == []

    store.set("OPENAI_API_KEY", "sk-abc")
    assert store.get("OPENAI_API_KEY") == "sk-abc"
    assert store.exists("OPENAI_API_KEY")
    assert store.source_of("OPENAI_API_KEY") == "file"
    assert store.list_names() == ["OPENAI_API_KEY"]
    # File is owner-only.
    assert oct((tmp_path / "secrets.env").stat().st_mode & 0o777) == "0o600"

    assert store.delete("OPENAI_API_KEY") is True
    assert store.delete("OPENAI_API_KEY") is False
    assert store.get("OPENAI_API_KEY") is None


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalSecretStore(tmp_path / "secrets.env")
    store.set("FIRECRAWL_API_KEY", "from-file")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "from-env")
    assert store.get("FIRECRAWL_API_KEY") == "from-env"
    assert store.source_of("FIRECRAWL_API_KEY") == "env"


def test_secret_name_validation() -> None:
    validate_secret_name("OPENAI_API_KEY")
    for bad in ("lowercase", "1STARTNUM", "has-dash", "has space", "", "A" * 200):
        with pytest.raises(InvalidSecretName):
            validate_secret_name(bad)


def test_secret_value_rejects_newlines(tmp_path: Path) -> None:
    store = LocalSecretStore(tmp_path / "secrets.env")
    with pytest.raises(InvalidSecretName):
        store.set("OPENAI_API_KEY", "line1\nline2")


# ----------------------------------------------------------------- openai runtime

OPENAI_SSE = (
    b'data: {"choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
    b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":4}}\n\n'
    b"data: [DONE]\n\n"
)


@respx.mock
async def test_openai_streams_deltas_usage_and_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=OPENAI_SSE)
    )
    runtime = OpenAIAgentRuntime()
    sctx = _ctx(tmp_path)
    sctx.settings["model"] = "gpt-4o-mini"
    await runtime.start_session(sctx)

    events: list = []

    async def on_event(e: object) -> None:
        events.append(e)

    result = await runtime.run_turn(sctx, "hi", on_event)
    assert route.called
    assert result.final_text == "Hello"
    assert result.usage.tokens_in == 12 and result.usage.tokens_out == 4
    # gpt-4o-mini pricing: 12/1e6*0.15 + 4/1e6*0.60 > 0
    assert result.usage.cost_usd > 0
    assert any(e.type is EventType.ASSISTANT_MESSAGE_DELTA for e in events)


@respx.mock
async def test_openai_bad_key_reports_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-bad")
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Invalid API key"}})
    )
    from cockpit.runtime.base import ProviderUnavailable

    runtime = OpenAIAgentRuntime()
    sctx = _ctx(tmp_path)
    await runtime.start_session(sctx)
    await runtime.send_input(sctx, "hi")
    with pytest.raises(ProviderUnavailable, match="rejected the API key"):
        async for _ in runtime.stream_events(sctx):
            pass


# ----------------------------------------------------------------- ollama runtime

OLLAMA_NDJSON = (
    b'{"message":{"role":"assistant","content":"Hi"},"done":false}\n'
    b'{"message":{"role":"assistant","content":" there"},"done":false}\n'
    b'{"message":{"content":""},"done":true,"prompt_eval_count":5,"eval_count":2}\n'
)


@respx.mock
async def test_ollama_streams_and_lists_models(tmp_path: Path) -> None:
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "llama3:latest"}, {"name": "qwen2:7b"}]}
        )
    )
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, content=OLLAMA_NDJSON)
    )
    from cockpit.runtime import ollama_runtime

    assert await ollama_runtime.list_models() == ["llama3:latest", "qwen2:7b"]

    runtime = OllamaAgentRuntime()
    sctx = _ctx(tmp_path)  # no model set → runtime picks the first installed one
    await runtime.start_session(sctx)

    async def on_event(e: object) -> None:
        pass

    result = await runtime.run_turn(sctx, "hi", on_event)
    assert result.final_text == "Hi there"
    assert result.usage.tokens_in == 5 and result.usage.tokens_out == 2
    assert result.usage.cost_usd == 0.0  # local inference is free


async def test_http_chat_interrupt_seam(tmp_path: Path) -> None:
    # The shared base tracks interrupt state per internal session (used to stop mid-stream).
    runtime = OpenAIAgentRuntime()
    sctx = _ctx(tmp_path)
    await runtime.start_session(sctx)
    assert runtime._is_interrupted(sctx) is False
    await runtime.interrupt(sctx)
    assert runtime._is_interrupted(sctx) is True
    await runtime.close_session(sctx)
    assert runtime._is_interrupted(sctx) is False


# ----------------------------------------------------------------- API endpoints


@pytest.fixture
async def client(app_env: dict) -> AsyncIterator[httpx.AsyncClient]:
    from cockpit.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def _onboard(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/onboarding",
        json={"user_name": "Testa", "enable_demo_data": False, "provider": "mock"},
    )
    assert resp.status_code == 201, resp.text


async def test_providers_endpoint_lists_real_providers(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # keep the curated list offline
    await _onboard(client)
    body = (await client.get("/api/v1/providers")).json()
    ids = {p["id"] for p in body["providers"]}
    assert {"mock", "claude", "openai", "ollama"} <= ids
    openai = next(p for p in body["providers"] if p["id"] == "openai")
    assert openai["requires_secret"] == "OPENAI_API_KEY"
    assert openai["default_model"] == "gpt-4o-mini"
    assert openai["models"]  # curated list even without a key


async def test_secrets_crud_never_returns_values(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    await _onboard(client)

    listing = (await client.get("/api/v1/secrets")).json()["secrets"]
    names = {s["name"] for s in listing}
    assert "OPENAI_API_KEY" in names
    openai_slot = next(s for s in listing if s["name"] == "OPENAI_API_KEY")
    assert openai_slot["configured"] is False

    # Set a value.
    put = await client.put("/api/v1/secrets/OPENAI_API_KEY", json={"value": "sk-secret"})
    assert put.status_code == 200
    assert "sk-secret" not in put.text  # value is never echoed

    after = (await client.get("/api/v1/secrets")).json()["secrets"]
    openai_slot = next(s for s in after if s["name"] == "OPENAI_API_KEY")
    assert openai_slot["configured"] is True and openai_slot["source"] == "file"
    assert "sk-secret" not in str(after)

    # Invalid name is rejected.
    bad = await client.put("/api/v1/secrets/not-valid", json={"value": "x"})
    assert bad.status_code == 400

    # Delete it.
    assert (await client.delete("/api/v1/secrets/OPENAI_API_KEY")).status_code == 204
    assert (await client.delete("/api/v1/secrets/OPENAI_API_KEY")).status_code == 404


async def test_env_secret_cannot_be_deleted_via_api(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "env-value")
    await _onboard(client)
    listing = (await client.get("/api/v1/secrets")).json()["secrets"]
    slot = next(s for s in listing if s["name"] == "FIRECRAWL_API_KEY")
    assert slot["source"] == "env" and slot["deletable"] is False
    resp = await client.delete("/api/v1/secrets/FIRECRAWL_API_KEY")
    assert resp.status_code == 409


async def test_connector_resource_add_and_remove(client: httpx.AsyncClient) -> None:
    await _onboard(client)
    add = await client.post(
        "/api/v1/connectors",
        json={"kind": "n8n_webhook", "name": "myflow", "url": "https://n8n.local/webhook/x"},
    )
    assert add.status_code == 201, add.text
    assert any(h["name"] == "myflow" for h in add.json()["config"]["webhooks"])

    removed = await client.delete("/api/v1/connectors/n8n/resources/myflow")
    assert removed.status_code == 200
    assert all(h["name"] != "myflow" for h in removed.json()["config"]["webhooks"])

    missing = await client.delete("/api/v1/connectors/n8n/resources/myflow")
    assert missing.status_code == 404


async def test_settings_reports_model_and_all_providers(client: httpx.AsyncClient) -> None:
    await _onboard(client)
    await client.patch("/api/v1/settings", json={"provider": "openai", "model": "gpt-4o"})
    settings = (await client.get("/api/v1/settings")).json()
    assert settings["provider"] == "openai" and settings["model"] == "gpt-4o"
    assert {"mock", "claude", "openai", "ollama"} <= set(settings["providers"])
