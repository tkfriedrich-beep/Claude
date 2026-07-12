"""Web Research connector + source-backed Research Run skill.

Connector tests exercise the SSRF guard, direct fetch/extraction, and search (offline demo +
Firecrawl-mocked) with no real network. Skill tests run the full worker pipeline with the web
connector's search/fetch stubbed, so the orchestration + memo synthesis are covered end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from cockpit.connectors.base import ConnectorError, ExecutionContext, ToolResult
from cockpit.connectors.web import WebResearchConnector, assert_public_http_url, html_to_text
from cockpit.registry import get_registry
from tests.conftest import get_run, submit_and_process

REPO_ROOT = Path(__file__).resolve().parents[3]
CONNECTORS = REPO_ROOT / "connectors"


def _ctx(config: dict[str, Any] | None = None) -> ExecutionContext:
    return ExecutionContext(workspace_id="w", run_id="r", correlation_id="c", config=config or {})


class FakeResp:
    def __init__(self, status=200, headers=None, content=b"", url="http://93.184.216.34/"):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.encoding = "utf-8"
        self.url = url

    def json(self) -> Any:
        import json

        return json.loads(self.content.decode())


class FakeStreamResp:
    """Minimal streamed-response stand-in for httpx.AsyncClient.stream (review R3-F12 uses it)."""

    def __init__(self, status=200, headers=None, content=b"", url="http://93.184.216.34/"):
        self.status_code = status
        self.headers = headers or {}
        self._content = content
        self.encoding = "utf-8"
        self.url = url

    async def aiter_bytes(self):
        yield self._content


def _patch_stream(monkeypatch: pytest.MonkeyPatch, resp_for) -> None:
    def stream(self, method, url, **kwargs):  # returns an async context manager (not a coroutine)
        class _CM:
            async def __aenter__(self_inner):
                return resp_for(url)

            async def __aexit__(self_inner, *a):
                return False

        return _CM()

    monkeypatch.setattr(httpx.AsyncClient, "stream", stream)


# --------------------------------------------------------------------------- SSRF guard
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/f",
        "http://0.0.0.0/",
    ],
)
async def test_ssrf_guard_blocks(url: str) -> None:
    with pytest.raises(ConnectorError):
        await assert_public_http_url(url)


async def test_ssrf_guard_allows_public_ip() -> None:
    await assert_public_http_url("http://93.184.216.34/")  # literal public IP, no DNS needed


def test_html_to_text_strips_scripts_and_head() -> None:
    title, body = html_to_text(
        "<html><head><title>Hi &amp; Bye</title></head>"
        "<body><script>evil()</script><p>Hello <b>world</b></p></body></html>"
    )
    assert title == "Hi & Bye"
    assert "Hello world" in body
    assert "evil" not in body  # script dropped
    assert "Bye" not in body  # head/title not leaked into body text


# --------------------------------------------------------------------------- fetch
async def test_fetch_extracts_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(
        monkeypatch,
        lambda url: FakeStreamResp(
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><head><title>Doc</title></head><body><p>Alpha beta.</p></body></html>",
            url=url,
        ),
    )
    connector = WebResearchConnector(CONNECTORS)
    result = await connector.execute("web.fetch", {"url": "http://93.184.216.34/doc"}, _ctx())
    assert result.ok
    assert result.data["title"] == "Doc"
    assert "Alpha beta." in result.data["content"]
    assert result.data["provider"] == "direct"


async def test_fetch_rejects_ssrf_target() -> None:
    connector = WebResearchConnector(CONNECTORS)
    with pytest.raises(ConnectorError, match="private/internal"):
        await connector.execute("web.fetch", {"url": "http://127.0.0.1/secret"}, _ctx())


async def test_fetch_revalidates_redirect_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A public URL that 302-redirects to the metadata IP must be blocked on the next hop."""
    _patch_stream(
        monkeypatch,
        lambda url: FakeStreamResp(
            status=302, headers={"location": "http://169.254.169.254/"}, url=url
        ),
    )
    connector = WebResearchConnector(CONNECTORS)
    with pytest.raises(ConnectorError, match="private/internal"):
        await connector.execute("web.fetch", {"url": "http://93.184.216.34/redir"}, _ctx())


async def test_fetch_rejects_binary_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_stream(
        monkeypatch,
        lambda url: FakeStreamResp(
            headers={"content-type": "image/png"}, content=b"\x89PNG", url=url
        ),
    )
    connector = WebResearchConnector(CONNECTORS)
    with pytest.raises(ConnectorError, match="non-text"):
        await connector.execute("web.fetch", {"url": "http://93.184.216.34/img"}, _ctx())


# --------------------------------------------------------------------------- search
async def test_search_offline_demo_is_labeled() -> None:
    connector = WebResearchConnector(CONNECTORS)  # no FIRECRAWL_API_KEY in test env
    result = await connector.execute("web.search", {"query": "why is the sky blue"}, _ctx())
    assert result.ok
    assert result.data["demo"] is True
    assert result.data["provider"] == "offline-demo"


async def test_search_firecrawl_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")

    async def fake_post(self, url, headers=None, json=None):
        assert headers["Authorization"] == "Bearer fc-test-key"
        return FakeResp(
            content=b'{"data":[{"title":"A","url":"https://a.example/","description":"d1"},'
            b'{"title":"B","url":"https://b.example/"}]}'
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    connector = WebResearchConnector(CONNECTORS)
    result = await connector.execute("web.search", {"query": "solar", "limit": 5}, _ctx())
    assert result.ok
    assert result.data["demo"] is False and result.data["provider"] == "firecrawl"
    urls = [r["url"] for r in result.data["results"]]
    assert urls == ["https://a.example/", "https://b.example/"]


# --------------------------------------------------------------------------- skill (pipeline)
def _stub_web(monkeypatch: pytest.MonkeyPatch, *, demo: bool) -> None:
    web = get_registry().connectors["web"]

    async def fake_search(inp, ctx):
        if demo:
            return ToolResult(
                ok=True, data={"results": [], "provider": "offline-demo", "demo": True}
            )
        return ToolResult(
            ok=True,
            data={
                "results": [
                    {"title": "Rayleigh scattering", "url": "http://93.184.216.34/a"},
                    {"title": "Sky color", "url": "http://93.184.216.34/b"},
                ],
                "provider": "firecrawl",
                "demo": False,
            },
        )

    async def fake_fetch(inp, ctx):
        return ToolResult(
            ok=True,
            data={
                "url": inp["url"],
                "title": "Rayleigh scattering",
                "content": "Shorter blue wavelengths scatter more than red in the atmosphere.",
                "truncated": False,
                "provider": "direct",
            },
        )

    monkeypatch.setattr(web, "_search", fake_search)
    monkeypatch.setattr(web, "_fetch", fake_fetch)


async def test_research_run_source_backed_extractive(
    workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With live sources but no provider, the memo is a source-backed extractive digest."""
    _stub_web(monkeypatch, demo=False)
    run_id = await submit_and_process(
        workspace["workspace_id"],
        kind="skill",
        skill_slug="research-run",
        input={"question": "why is the sky blue"},
    )
    run = await get_run(run_id)
    assert run.status == "completed"
    assert run.result["data"]["mode"] == "source_backed"
    assert run.result["data"]["source_count"] == 2

    from sqlalchemy import select

    from cockpit.db import db_session
    from cockpit.models import Artifact

    async with db_session() as session:
        art = (await session.scalars(select(Artifact).where(Artifact.run_id == run_id))).first()
    body = (workspace["settings"].artifacts_dir / art.path).read_text()
    assert "## Sources" in body
    assert "93.184.216.34/a" in body  # a real fetched URL is cited


async def test_research_run_knowledge_fallback_when_search_is_demo(
    workspace: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Offline demo search (no live results) with no provider fails cleanly, not silently."""
    _stub_web(monkeypatch, demo=True)
    run_id = await submit_and_process(
        workspace["workspace_id"],
        kind="skill",
        skill_slug="research-run",
        input={"question": "why is the sky blue"},
    )
    run = await get_run(run_id)
    # No live sources and no model provider in the test env → clean failure with guidance.
    assert run.status == "failed"
