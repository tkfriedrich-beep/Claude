"""Web Research connector — read-only web search + page fetch for the Research Run skill.

Boundaries that matter:
- `web.fetch` is guarded against SSRF: only http(s), and the host must resolve entirely to
  public addresses (private/loopback/link-local/reserved/metadata IPs are refused). Redirects
  are followed manually so every hop is re-validated — a 302 to `http://169.254.169.254` is
  rejected, not followed.
- `web.search` is Firecrawl-backed when `FIRECRAWL_API_KEY` is set; otherwise it returns a
  clearly `demo`-labeled placeholder so the skill runs credential-less (mirrors the mock
  runtime). Fetch is always the direct, keyless, SSRF-guarded path.
- Retrieved content is untrusted *data*, never instructions — the skill frames it as such.
  Secrets are referenced by env-var name and resolved through SecretStore at call time.
"""

from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from cockpit.connectors.base import (
    BaseConnector,
    ConnectorError,
    ExecutionContext,
    HealthStatus,
    ToolResult,
)
from cockpit.enums import ConnectorHealthState
from cockpit.logging import redact_text
from cockpit.secrets import get_secret_store

DEFAULT_API_KEY_ENV = "FIRECRAWL_API_KEY"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
USER_AGENT = "AgenticOS-Cockpit/0.1 (+research-run; read-only)"
MAX_FETCH_BYTES = 1_500_000
MAX_REDIRECTS = 4


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


async def assert_public_http_url(url: str) -> None:
    """Raise ConnectorError unless `url` is an http(s) URL whose host is entirely public.

    Blocks SSRF to loopback/private/link-local/reserved ranges — including the cloud metadata
    endpoint (169.254.169.254, a link-local address). Called for every request AND every
    redirect hop, so a public URL cannot redirect into the internal network.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ConnectorError(f"Refusing to fetch a non-http(s) URL (scheme “{parsed.scheme}”).")
    host = parsed.hostname
    if not host:
        raise ConnectorError("Refusing to fetch a URL with no host.")
    # Literal IP host — classify directly.
    try:
        ipaddress.ip_address(host)
        if not _ip_is_public(host):
            raise ConnectorError(f"Refusing to fetch a private/internal address ({host}).")
        return
    except ValueError:
        pass  # it's a hostname; resolve and classify every answer
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except OSError as exc:
        raise ConnectorError(f"Could not resolve host “{host}”.") from exc
    ips = {str(info[4][0]) for info in infos}
    if not ips:
        raise ConnectorError(f"Could not resolve host “{host}”.")
    if any(not _ip_is_public(ip) for ip in ips):
        raise ConnectorError(
            f"Refusing to fetch “{host}” — it resolves to a private/internal address."
        )


def html_to_text(raw_html: str) -> tuple[str, str]:
    """Small HTML→text reducer (no dependency): title + de-tagged, whitespace-collapsed body."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    body = re.sub(
        r"<(head|script|style|noscript|template|svg)\b.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html_module.unescape(body)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    body = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)+", "\n\n", body)
    return html_module.unescape(title), body.strip()


class WebResearchConnector(BaseConnector):
    slug = "web"

    def __init__(self, manifest_dir: Path) -> None:
        super().__init__(manifest_dir)
        self.runtime_config: dict[str, Any] = {}

    def _config(self, ctx: ExecutionContext) -> dict[str, Any]:
        return (ctx.config or None) or self.runtime_config

    def _api_key_env(self, ctx: ExecutionContext) -> str:
        return str(self._config(ctx).get("api_key_env") or DEFAULT_API_KEY_ENV)

    def _search_provider(self, ctx: ExecutionContext) -> str:
        explicit = self._config(ctx).get("search_provider")
        if explicit:
            return str(explicit)
        return "firecrawl" if get_secret_store().exists(self._api_key_env(ctx)) else "offline"

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        if self._search_provider(ctx) == "firecrawl":
            detail = "search: Firecrawl (live); fetch: direct (SSRF-guarded)"
        else:
            detail = (
                f"search: offline demo (set {self._api_key_env(ctx)} for live search); "
                "fetch: direct (SSRF-guarded)"
            )
        return HealthStatus(ConnectorHealthState.OK, detail)

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        if tool_id == "web.search":
            return await self._search(validated_input, ctx)
        if tool_id == "web.fetch":
            return await self._fetch(validated_input, ctx)
        raise ConnectorError(f"unknown tool {tool_id}")

    # ---------------------------------------------------------------- search
    async def _search(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        query = inp["query"]
        limit = int(inp.get("limit", 5))
        if self._search_provider(ctx) == "firecrawl":
            return await self._search_firecrawl(query, limit, ctx)
        # Offline fallback: clearly demo-labeled so the UI/payload never implies live sources.
        results = [
            {
                "title": f"[demo] {query} — placeholder result",
                "url": "https://example.com/",
                "snippet": (
                    "Offline demo result. Set FIRECRAWL_API_KEY (Integrations → Web Research) "
                    "for live web search. Fetching still works on any public URL."
                ),
            }
        ]
        return ToolResult(
            ok=True,
            data={"results": results[:limit], "provider": "offline-demo", "demo": True},
            summary=f"(demo) placeholder search for “{query[:60]}” — no live provider configured.",
        )

    async def _search_firecrawl(self, query: str, limit: int, ctx: ExecutionContext) -> ToolResult:
        key = get_secret_store().get(self._api_key_env(ctx))
        if not key:
            raise ConnectorError(
                f"Search provider is Firecrawl but {self._api_key_env(ctx)} is not set."
            )
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(
                    FIRECRAWL_SEARCH_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={"query": query, "limit": limit},
                )
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Search provider unreachable: {redact_text(str(exc))}") from exc
        if resp.status_code >= 400:
            raise ConnectorError(f"Search provider returned HTTP {resp.status_code}.")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ConnectorError("Search provider returned non-JSON output.") from exc
        items = payload.get("data") or payload.get("results") or []
        results = []
        for it in items:
            if not isinstance(it, dict):
                continue
            url = it.get("url") or it.get("link")
            if not url:
                continue
            results.append(
                {
                    "title": it.get("title") or it.get("name") or "",
                    "url": url,
                    "snippet": it.get("description") or it.get("snippet") or "",
                }
            )
        return ToolResult(
            ok=True,
            data={"results": results[:limit], "provider": "firecrawl", "demo": False},
            summary=f"{len(results[:limit])} live result(s) for “{query[:60]}”.",
        )

    # ---------------------------------------------------------------- fetch
    async def _fetch(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        start_url = inp["url"]
        max_chars = int(inp.get("max_chars", 8000))
        max_bytes = int(self._config(ctx).get("max_bytes") or MAX_FETCH_BYTES)
        current = start_url
        resp: httpx.Response | None = None
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=25, headers={"User-Agent": USER_AGENT}
        ) as client:
            for _hop in range(MAX_REDIRECTS):
                await assert_public_http_url(current)  # re-check EVERY hop (SSRF via redirect)
                try:
                    resp = await client.get(current)
                except httpx.HTTPError as exc:
                    raise ConnectorError(f"Fetch failed: {redact_text(str(exc))}") from exc
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    current = urljoin(current, resp.headers["location"])
                    continue
                break
            else:
                raise ConnectorError("Too many redirects — refusing to keep following.")
        assert resp is not None
        if resp.status_code >= 400:
            raise ConnectorError(f"Fetch failed: HTTP {resp.status_code} for {current}.")
        ctype = resp.headers.get("content-type", "").lower()
        if ctype and not any(t in ctype for t in ("html", "text/plain", "xml", "json")):
            raise ConnectorError(f"Refusing non-text content ({ctype}).")
        raw = resp.content[:max_bytes]
        decoded = raw.decode(resp.encoding or "utf-8", errors="replace")
        if "html" in ctype or "<html" in decoded[:2000].lower():
            title, content = html_to_text(decoded)
        else:
            title, content = "", decoded.strip()
        truncated = len(content) > max_chars or len(resp.content) > max_bytes
        return ToolResult(
            ok=True,
            data={
                "url": str(resp.url),
                "title": title,
                "content": content[:max_chars],
                "truncated": truncated,
                "provider": "direct",
            },
            summary=f"Fetched {title or current} ({len(content[:max_chars])} chars).",
        )
