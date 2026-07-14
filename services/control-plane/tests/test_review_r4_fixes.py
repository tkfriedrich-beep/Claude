"""Regression tests for Codex adversarial review R4.

Only F1 (the phone/LAN exposure) has a backend-testable surface; the other eleven findings are
front-end and are covered by web unit tests + Playwright specs. F1 is the Critical one, so it
gets thorough coverage here: the pure trust decision, plus proof the middleware actually rejects
an unauthenticated remote mutation before it can reach settings/Safe Mode.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

import cockpit.config as config_module
from cockpit.netguard import client_is_trusted

TAILNET = "100.64.0.0/10"


# ---------------------------------------------------------------- pure decision (F1)


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "::1", "100.64.0.1", "100.100.20.30", "100.127.255.254"],
)
def test_loopback_and_tailnet_are_trusted(host: str) -> None:
    assert client_is_trusted(host, TAILNET) is True


@pytest.mark.parametrize(
    "host",
    [
        "192.168.1.10",  # home LAN
        "10.0.0.5",  # private LAN
        "172.16.0.9",  # private LAN
        "8.8.8.8",  # public
        "100.63.255.255",  # just below the CGNAT range
        "100.128.0.0",  # just above the CGNAT range
    ],
)
def test_lan_and_public_are_rejected(host: str) -> None:
    assert client_is_trusted(host, TAILNET) is False


def test_missing_or_nonip_host_is_local_not_remote() -> None:
    # In-process ASGI callers (no client, or Starlette's "testclient") are never a network peer.
    assert client_is_trusted(None, TAILNET) is True
    assert client_is_trusted("", TAILNET) is True
    assert client_is_trusted("testclient", TAILNET) is True


def test_trusted_networks_is_configurable() -> None:
    # Empty spec → loopback only; wildcard → everything; a malformed entry never widens access.
    assert client_is_trusted("8.8.8.8", "") is False
    assert client_is_trusted("127.0.0.1", "") is True
    assert client_is_trusted("8.8.8.8", "0.0.0.0/0") is True
    assert client_is_trusted("192.168.1.5", "not-a-cidr, 192.168.0.0/16") is True
    assert client_is_trusted("8.8.8.8", "not-a-cidr") is False


# ------------------------------------------------------------ middleware integration (F1)


def _client(app_env: dict, host: str) -> httpx.AsyncClient:
    from cockpit.main import create_app

    # ASGITransport lets us stamp the ASGI scope's client address — i.e. simulate the remote peer.
    transport = httpx.ASGITransport(app=create_app(), client=(host, 51000))
    return httpx.AsyncClient(transport=transport, base_url="http://otto.test")


async def test_untrusted_client_is_blocked_before_any_mutation(app_env: dict) -> None:
    async with _client(app_env, "203.0.113.7") as remote:
        # A non-browser client on the LAN/public net cannot even read health…
        health = await remote.get("/api/v1/health")
        assert health.status_code == 403
        assert health.headers["content-type"].startswith("application/problem+json")
        # …and crucially cannot flip Safe Mode off (Codex's exact takeover scenario).
        patched = await remote.patch("/api/v1/settings", json={"safe_mode": False})
        assert patched.status_code == 403


async def test_loopback_client_passes_the_guard(app_env: dict) -> None:
    async with _client(app_env, "127.0.0.1") as local:
        resp = await local.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


async def test_tailnet_client_passes_the_guard(app_env: dict) -> None:
    async with _client(app_env, "100.100.4.5") as peer:
        resp = await peer.get("/api/v1/health")
        assert resp.status_code == 200


async def test_trusted_networks_env_override_opens_the_lan(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    # Opt-in widening: with the LAN explicitly trusted, a LAN client is allowed through.
    monkeypatch.setenv("COCKPIT_DATA_DIR", str(tmp_path / "local"))
    monkeypatch.setenv("COCKPIT_START_BACKGROUND_TASKS", "false")
    monkeypatch.setenv("COCKPIT_TRUSTED_NETWORKS", "192.168.0.0/16")
    config_module.get_settings.cache_clear()
    from cockpit.main import create_app

    transport = httpx.ASGITransport(app=create_app(), client=("192.168.1.22", 51000))
    async with httpx.AsyncClient(transport=transport, base_url="http://otto.test") as lan:
        resp = await lan.get("/api/v1/health")
        assert resp.status_code == 200
    config_module.get_settings.cache_clear()
