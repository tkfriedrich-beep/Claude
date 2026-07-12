"""Web Research connector — read-only web search + page fetch for the Research Run skill.

Boundaries that matter:
- `web.fetch` is guarded against SSRF: only http(s); the host must resolve entirely to public
  addresses; credentials in the URL (userinfo) are refused; and the connection is **pinned to the
  validated IP** — httpx connects to that exact address (Host header + TLS SNI preserved) so a
  DNS-rebinding flip between the guard's lookup and the socket connect cannot reach an internal
  service (review R3-F1). Every redirect hop is re-validated and re-pinned.
- The response body is **streamed with a hard byte cap** (no full buffering), and HTML→text uses a
  linear scanner (no catastrophic regex), so one hostile page cannot exhaust memory or block the
  event loop (review R3-F12).
- `web.search` is Firecrawl-backed when `FIRECRAWL_API_KEY` is set; otherwise a clearly
  `demo`-labeled placeholder. The API-key env var name is **fixed in code** — connector config can
  never redirect it at another process secret (review R3-F4).
- Retrieved content is untrusted *data*, never instructions — the skill frames it as such.
"""

from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import re
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse

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

# Fixed in code — never sourced from connector config, so a config edit can't point the web
# connector at ANTHROPIC_API_KEY (or any other env secret) and exfiltrate it (review R3-F4).
API_KEY_ENV = "FIRECRAWL_API_KEY"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
USER_AGENT = "AgenticOS-Cockpit/0.1 (+research-run; read-only)"
MAX_FETCH_BYTES = 1_500_000
MAX_REDIRECTS = 4
_BLOCK_TAGS = ("head", "script", "style", "noscript", "template", "svg")


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped  # classify ::ffff:127.0.0.1 by its embedded IPv4
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


async def _validate_and_pin(url: str) -> tuple[str, str, str, str]:
    """Validate `url` for SSRF and return (ip_url, host_header, sni_host, scheme).

    `ip_url` has the host replaced by a **validated public IP** so httpx connects to that exact
    address with no second DNS lookup (closes the rebinding TOCTOU — R3-F1). The original host is
    carried as the Host header and TLS SNI so routing and cert verification still work.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ConnectorError(f"Refusing to fetch a non-http(s) URL (scheme “{parsed.scheme}”).")
    if parsed.username or parsed.password:  # R3-F5 — never send/persist URL-embedded credentials
        raise ConnectorError("Refusing to fetch a URL that embeds credentials (user:pass@).")
    host = parsed.hostname
    if not host:
        raise ConnectorError("Refusing to fetch a URL with no host.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        ipaddress.ip_address(host)  # literal IP host
        if not _ip_is_public(host):
            raise ConnectorError(f"Refusing to fetch a private/internal address ({host}).")
        pinned = host
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port)
        except OSError as exc:
            raise ConnectorError(f"Could not resolve host “{host}”.") from exc
        ips = [str(info[4][0]) for info in infos]
        if not ips:
            raise ConnectorError(f"Could not resolve host “{host}”.") from None
        if any(not _ip_is_public(ip) for ip in ips):
            raise ConnectorError(
                f"Refusing to fetch “{host}” — it resolves to a private/internal address."
            ) from None
        pinned = ips[0]

    netloc = f"[{pinned}]" if ":" in pinned else pinned
    if parsed.port:
        netloc += f":{parsed.port}"
    ip_url = urlunparse(
        ParseResult(parsed.scheme, netloc, parsed.path or "/", parsed.params, parsed.query, "")
    )
    return ip_url, parsed.netloc, host, parsed.scheme


async def assert_public_http_url(url: str) -> None:
    """Raise ConnectorError unless `url` is a fetchable public http(s) URL (SSRF-safe, no creds)."""
    await _validate_and_pin(url)


def _strip_tag_blocks(html_str: str, tags: tuple[str, ...]) -> str:
    """Linear removal of <tag>…</tag> blocks (script/style/head/…) — no backtracking regex.

    The prior `<(script|…)>.*?</\\1>` with DOTALL was O(n²) on unclosed tags (a ReDoS —
    review R3-F12). This scans with str.find, which is linear.
    """
    lower = html_str.lower()
    out: list[str] = []
    i, n = 0, len(html_str)
    while i < n:
        nxt, found = -1, ""
        for t in tags:
            idx = lower.find("<" + t, i)
            if idx != -1 and (nxt == -1 or idx < nxt):
                after = lower[idx + 1 + len(t) : idx + 2 + len(t)]
                if after in (" ", ">", "/", "\t", "\n", "\r", ""):
                    nxt, found = idx, t
        if nxt == -1:
            out.append(html_str[i:])
            break
        out.append(html_str[i:nxt])
        close = lower.find("</" + found, nxt)
        if close == -1:
            break  # unclosed block → drop the remainder
        gt = lower.find(">", close)
        i = gt + 1 if gt != -1 else n
    return "".join(out)


def html_to_text(raw_html: str) -> tuple[str, str]:
    """Small HTML→text reducer (no dependency): title + de-tagged, whitespace-collapsed body."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    body = _strip_tag_blocks(raw_html, _BLOCK_TAGS)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    body = re.sub(r"<[^>]+>", " ", body)  # linear: [^>]+ cannot backtrack catastrophically
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

    def _search_provider(self, ctx: ExecutionContext) -> str:
        explicit = self._config(ctx).get("search_provider")
        if explicit:
            return str(explicit)
        return "firecrawl" if get_secret_store().exists(API_KEY_ENV) else "offline"

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        if self._search_provider(ctx) == "firecrawl":
            detail = "search: Firecrawl (live); fetch: direct (SSRF-guarded, IP-pinned)"
        else:
            detail = (
                f"search: offline demo (set {API_KEY_ENV} for live search); "
                "fetch: direct (SSRF-guarded, IP-pinned)"
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
            return await self._search_firecrawl(query, limit)
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

    async def _search_firecrawl(self, query: str, limit: int) -> ToolResult:
        key = get_secret_store().get(API_KEY_ENV)
        if not key:
            raise ConnectorError(f"Search provider is Firecrawl but {API_KEY_ENV} is not set.")
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(
                    FIRECRAWL_SEARCH_URL,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
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
        current = inp["url"]
        max_chars = int(inp.get("max_chars", 8000))
        max_bytes = int(self._config(ctx).get("max_bytes") or MAX_FETCH_BYTES)
        async with httpx.AsyncClient(follow_redirects=False, timeout=25) as client:
            for _hop in range(MAX_REDIRECTS):
                ip_url, host_header, sni_host, scheme = await _validate_and_pin(current)
                headers = {"User-Agent": USER_AGENT, "Host": host_header}
                extensions = {"sni_hostname": sni_host} if scheme == "https" else {}
                try:
                    async with client.stream(
                        "GET", ip_url, headers=headers, extensions=extensions
                    ) as resp:
                        if (
                            resp.status_code in (301, 302, 303, 307, 308)
                            and "location" in resp.headers
                        ):
                            current = urljoin(current, resp.headers["location"])
                            continue  # re-validate + re-pin the next hop; body not read
                        if resp.status_code >= 400:
                            raise ConnectorError(
                                f"Fetch failed: HTTP {resp.status_code} for {current}."
                            )
                        ctype = resp.headers.get("content-type", "").lower()
                        if ctype and not any(
                            t in ctype for t in ("html", "text/plain", "xml", "json")
                        ):
                            raise ConnectorError(f"Refusing non-text content ({ctype}).")
                        buf = bytearray()
                        capped = False
                        async for chunk in resp.aiter_bytes():
                            buf += chunk
                            if len(buf) >= max_bytes:  # hard cap BEFORE buffering more (R3-F12)
                                capped = True
                                break
                        decoded = bytes(buf[:max_bytes]).decode(
                            resp.encoding or "utf-8", errors="replace"
                        )
                except httpx.HTTPError as exc:
                    raise ConnectorError(f"Fetch failed: {redact_text(str(exc))}") from exc
                if "html" in ctype or "<html" in decoded[:2000].lower():
                    title, content = html_to_text(decoded)
                else:
                    title, content = "", decoded.strip()
                return ToolResult(
                    ok=True,
                    data={
                        "url": current,
                        "title": title,
                        "content": content[:max_chars],
                        "truncated": capped or len(content) > max_chars,
                        "provider": "direct",
                    },
                    summary=f"Fetched {title or current} ({len(content[:max_chars])} chars).",
                )
            raise ConnectorError("Too many redirects — refusing to keep following.")
