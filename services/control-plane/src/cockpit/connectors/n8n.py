"""n8n connector — signed webhook invocation with schema-bound inputs/outputs.

Webhooks are registered per-workspace (Integrations screen / POST /connectors). Each becomes a
tool `n8n.<name>`. Requests are HMAC-signed; the secret is referenced by *env var name* and
resolved through SecretStore at call time — never stored in the DB.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import httpx

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
from cockpit.secrets import get_secret_store


class N8nConnector(BaseConnector):
    slug = "n8n"

    def __init__(self, manifest_dir: Path) -> None:
        super().__init__(manifest_dir)
        self.runtime_config: dict[str, Any] = {}

    def _webhooks_in(self, config: dict[str, Any] | None) -> list[dict[str, Any]]:
        # config=None → the process-global singleton (runtime_config); an explicit dict (even {})
        # → THAT workspace's config verbatim. The gateway resolves a tool's manifest by passing the
        # workspace's DB Connector.config here, so policy/durability/execution all describe the same
        # webhook — never another workspace's singleton state (review R3-F2, R2-F8).
        src = self.runtime_config if config is None else config
        return list((src or {}).get("webhooks", []))

    def _webhooks(self, ctx: ExecutionContext | None = None) -> list[dict[str, Any]]:
        # Execution/health path: ctx.config is this workspace's config (empty {} → fall back to the
        # singleton is safe here because policy already resolved the tool against the strict
        # per-workspace manifest before we ever execute).
        return self._webhooks_in((ctx.config or None) if ctx is not None else None)

    def list_tools(self, config: dict[str, Any] | None = None) -> list[ToolManifest]:
        tools: list[ToolManifest] = []
        for hook in self._webhooks_in(config):
            read_only = bool(hook.get("read_only", False))
            tools.append(
                ToolManifest(
                    id=f"n8n.{hook['name']}",
                    connector=self.slug,
                    name=f"n8n workflow: {hook['name']}",
                    description=hook.get("description", "Registered n8n webhook workflow"),
                    capability="workflow",
                    input_schema=hook.get("input_schema", {"type": "object"}),
                    output_schema=hook.get("output_schema", {"type": "object"}),
                    access=ToolAccess.READ if read_only else ToolAccess.WRITE,
                    risk_level=RiskLevel.R1 if read_only else RiskLevel.R3,
                    # A webhook always leaves this machine — it has external side effects even
                    # when the user labels it "read only" (which only lowers the risk label).
                    external_side_effects=True,
                    supports_dry_run=bool(hook.get("supports_dry_run", False)),
                    idempotent=False,
                    timeout_seconds=int(hook.get("timeout_seconds", 60)),
                    retry=RetryPolicy(max_attempts=1),
                    approval="required",
                    # User-registered at runtime → never auto-run on its own classification.
                    trusted=False,
                    undo_strategy=hook.get("undo_strategy", ""),
                )
            )
        return tools

    def get_tool(self, tool_id: str, config: dict[str, Any] | None = None) -> ToolManifest | None:
        return next((t for t in self.list_tools(config) if t.id == tool_id), None)

    def owns_tool(self, tool_id: str) -> bool:
        return tool_id.startswith("n8n.")

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        hooks = self._webhooks(ctx)
        if not hooks:
            return HealthStatus(ConnectorHealthState.DEGRADED, "No webhooks registered yet")
        missing = [
            h["name"]
            for h in hooks
            if h.get("secret_env") and not get_secret_store().exists(h["secret_env"])
        ]
        if missing:
            return HealthStatus(
                ConnectorHealthState.DEGRADED,
                f"Missing HMAC secret env for: {', '.join(missing)}",
            )
        return HealthStatus(ConnectorHealthState.OK, f"{len(hooks)} webhook(s) registered")

    async def preview(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        # A preview must be side-effect free. We cannot know a workflow's real diff without
        # calling it, and calling it IS an external effect (a hostile/buggy workflow can ignore
        # a `dry_run` flag) — so the honest preview is a LOCAL description of the request that
        # would be sent, with no HTTP at all (review R2-F2).
        name = tool_id.removeprefix("n8n.")
        hook = next((h for h in self._webhooks(ctx) if h["name"] == name), None)
        if hook is None:
            raise ConnectorError(f"n8n webhook “{name}” is not registered.")
        payload = json.dumps(validated_input, ensure_ascii=False)
        return ToolResult(
            ok=True,
            data={
                "preview": True,
                "diff": f"Would POST to n8n workflow “{name}” ({hook.get('url', '?')}):\n"
                f"{payload[:800]}",
            },
            summary=f"Preview: would call n8n workflow “{name}” — no request sent.",
        )

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        assert not ctx.dry_run, "real n8n invoke called for a dry-run"
        return await self._invoke(tool_id, validated_input, ctx)

    async def _invoke(
        self,
        tool_id: str,
        validated_input: dict[str, Any],
        ctx: ExecutionContext,
    ) -> ToolResult:
        name = tool_id.removeprefix("n8n.")
        hook = next((h for h in self._webhooks(ctx) if h["name"] == name), None)
        if hook is None:
            raise ConnectorError(f"n8n webhook “{name}” is not registered.")

        body = json.dumps(
            {
                "dry_run": False,
                "payload": validated_input,
                "correlation_id": ctx.correlation_id,
            },
            ensure_ascii=False,
        ).encode()
        # Idempotency key must cover the actual input, not just run+tool — otherwise two
        # distinct calls to the same webhook in one run collide and a caching workflow returns
        # the first response for the second (a silent no-op reported as success — review R2-F6).
        canonical = json.dumps(validated_input, sort_keys=True, ensure_ascii=False)
        headers = {
            "Content-Type": "application/json",
            "X-Cockpit-Idempotency-Key": hashlib.sha256(
                f"{ctx.run_id}|{tool_id}|{canonical}".encode()
            ).hexdigest()[:32],
            "X-Correlation-Id": ctx.correlation_id,
        }
        secret_env = hook.get("secret_env")
        if secret_env:
            secret = get_secret_store().get(secret_env)
            if not secret:
                raise ConnectorError(f"HMAC secret “{secret_env}” is not set in the environment.")
            headers["X-Cockpit-Signature"] = (
                "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            )

        timeout = int(hook.get("timeout_seconds", 60))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(hook["url"], content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ConnectorError(f"n8n webhook unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise ConnectorError(
                f"n8n webhook returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            data = response.json()
            if not isinstance(data, dict):
                data = {"result": data}
        except ValueError as exc:
            raise ConnectorError("n8n webhook returned non-JSON output.") from exc

        return ToolResult(
            ok=True,
            data=data,
            summary=f"n8n workflow “{name}” executed",
            external_confirmed=True,
        )
