"""Generic MCP connector registry.

MCP is a transport, not the domain model: discovered tools are normalized into the same
ToolManifest the gateway uses everywhere, then local policy applies (default: writes are R3 +
approval; reads R1). Server output is untrusted data — schema-validated and redacted.

Transports:
- "stdio": official `mcp` python SDK (optional dependency); a fresh short-lived session per
  call keeps lifecycle simple and crash-safe for the local MVP.
- "inproc": an in-process demo/test server (data/demo-backed), no subprocesses involved.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cockpit.connectors.base import (
    BaseConnector,
    ConnectorError,
    ExecutionContext,
    HealthStatus,
    RetryPolicy,
    ToolManifest,
    ToolResult,
)
from cockpit.enums import ConnectorHealthState, RiskLevel, ToolAccess
from cockpit.logging import get_logger

log = get_logger("cockpit.mcp")

# In-proc demo server: proves the normalize-and-govern path without external processes.
INPROC_TOOLS: dict[str, dict[str, Any]] = {
    "echo": {
        "description": "Echo back a message (demo tool)",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        "read_only": True,
    },
    "todo_add": {
        "description": "Add a todo item to the demo MCP store (demo write tool)",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "read_only": False,
    },
}
_inproc_store: list[str] = []


def normalize_mcp_tool(
    server_name: str,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    *,
    read_only: bool,
    trusted: bool = False,
) -> ToolManifest:
    # `trusted=False` (the default for discovered/remote servers) means the policy won't
    # auto-run the tool on the server's self-declared readOnlyHint — a registered MCP server
    # is not a grant of trust. The built-in in-process demo server passes trusted=True.
    external = not (trusted and read_only)
    return ToolManifest(
        id=f"mcp.{server_name}.{name}",
        connector="mcp",
        name=f"{server_name}: {name}",
        description=description or "MCP tool",
        capability="mcp",
        input_schema=input_schema or {"type": "object"},
        output_schema={"type": "object"},  # MCP results are normalized to {content: ...}
        access=ToolAccess.READ if read_only else ToolAccess.WRITE,
        risk_level=RiskLevel.R1 if read_only else RiskLevel.R3,
        external_side_effects=external,
        supports_dry_run=False,
        idempotent=False,
        timeout_seconds=45,
        retry=RetryPolicy(max_attempts=1),
        approval="auto" if (read_only and trusted) else "required",
        trusted=trusted,
    )


class MCPConnector(BaseConnector):
    slug = "mcp"

    def __init__(self, manifest_dir: Path) -> None:
        super().__init__(manifest_dir)
        self.runtime_config: dict[str, Any] = {}

    def _servers(self, ctx: ExecutionContext | None = None) -> list[dict[str, Any]]:
        # On the execution path, prefer THIS workspace's config (threaded in via ctx.config from
        # the DB Connector row) over the global singleton's runtime_config, so a call never routes
        # to another workspace's MCP server if it refreshed the singleton in between (R2-F8).
        source = (
            ctx.config
            if ctx is not None and ctx.config.get("servers") is not None
            else self.runtime_config
        )
        return [s for s in source.get("servers", []) if s.get("enabled", True)]

    def list_tools(self) -> list[ToolManifest]:
        tools: list[ToolManifest] = []
        for server in self._servers():
            if server.get("transport") == "inproc":
                for name, spec in INPROC_TOOLS.items():
                    tools.append(
                        normalize_mcp_tool(
                            server["name"],
                            name,
                            spec["description"],
                            spec["input_schema"],
                            read_only=spec["read_only"],
                            trusted=True,  # built-in demo server, in-process (no external call)
                        )
                    )
            else:
                for t in server.get("discovered_tools", []):
                    tools.append(
                        normalize_mcp_tool(
                            server["name"],
                            t["name"],
                            t.get("description", ""),
                            t.get("input_schema", {"type": "object"}),
                            read_only=bool(t.get("read_only", False)),
                        )
                    )
        return tools

    def get_tool(self, tool_id: str) -> ToolManifest | None:
        return next((t for t in self.list_tools() if t.id == tool_id), None)

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        servers = self._servers(ctx)
        if not servers:
            return HealthStatus(ConnectorHealthState.DEGRADED, "No MCP servers registered yet")
        details = []
        state = ConnectorHealthState.OK
        for server in servers:
            if server.get("transport") == "inproc":
                details.append(f"{server['name']}: ok (in-process demo)")
            elif server.get("transport") == "stdio":
                try:
                    tools = await discover_stdio_tools(server, timeout=8)
                    details.append(f"{server['name']}: ok ({len(tools)} tools)")
                except Exception as exc:
                    state = ConnectorHealthState.DEGRADED
                    details.append(f"{server['name']}: unreachable ({exc})")
            else:
                state = ConnectorHealthState.DEGRADED
                details.append(f"{server['name']}: unsupported transport")
        return HealthStatus(state, "; ".join(details))

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        _, server_name, tool_name = tool_id.split(".", 2)
        server = next((s for s in self._servers(ctx) if s["name"] == server_name), None)
        if server is None:
            raise ConnectorError(f"MCP server “{server_name}” is not registered/enabled.")

        if server.get("transport") == "inproc":
            return self._execute_inproc(tool_name, validated_input, ctx)
        if server.get("transport") == "stdio":
            content = await call_stdio_tool(server, tool_name, validated_input, timeout=40)
            return ToolResult(
                ok=True,
                data={"content": content},
                summary=f"MCP {server_name}.{tool_name} completed",
                external_confirmed=True,
            )
        raise ConnectorError(f"Unsupported MCP transport for “{server_name}”.")

    def _execute_inproc(
        self, tool_name: str, inp: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        if tool_name == "echo":
            return ToolResult(
                ok=True, data={"content": inp["message"]}, summary="Echoed message (demo MCP)"
            )
        if tool_name == "todo_add":
            # MCP tools declare supports_dry_run=False, so the gateway never routes a preview
            # here (there is no standard MCP dry-run). This is always the real effect.
            assert not ctx.dry_run, "MCP tools have no preview path"
            _inproc_store.append(inp["text"])
            return ToolResult(
                ok=True,
                data={"content": f"added ({len(_inproc_store)} total)"},
                summary="Added todo in demo MCP store",
                external_confirmed=True,
            )
        raise ConnectorError(f"unknown in-proc MCP tool {tool_name}")


async def discover_stdio_tools(server: dict[str, Any], *, timeout: int) -> list[dict[str, Any]]:
    """Connect to a stdio MCP server and list tools. Requires the optional `mcp` package."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise ConnectorError(
            "The `mcp` package is not installed — install with: uv sync --extra mcp"
        ) from exc

    params = StdioServerParameters(
        command=server["command"], args=server.get("args", []), env=server.get("env")
    )

    async def _inner() -> list[dict[str, Any]]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for t in result.tools:
                    annotations = getattr(t, "annotations", None)
                    read_only = bool(getattr(annotations, "readOnlyHint", False))
                    tools.append(
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": t.inputSchema or {"type": "object"},
                            "read_only": read_only,
                        }
                    )
                return tools

    return await asyncio.wait_for(_inner(), timeout=timeout)


async def call_stdio_tool(
    server: dict[str, Any], tool_name: str, arguments: dict[str, Any], *, timeout: int
) -> Any:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise ConnectorError(
            "The `mcp` package is not installed — install with: uv sync --extra mcp"
        ) from exc

    params = StdioServerParameters(
        command=server["command"], args=server.get("args", []), env=server.get("env")
    )

    async def _inner() -> Any:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                out: list[Any] = []
                for block in result.content:
                    text = getattr(block, "text", None)
                    out.append(text if text is not None else str(block))
                if getattr(result, "isError", False):
                    raise ConnectorError(f"MCP tool error: {' '.join(map(str, out))[:300]}")
                return out if len(out) != 1 else out[0]

    return await asyncio.wait_for(_inner(), timeout=timeout)
