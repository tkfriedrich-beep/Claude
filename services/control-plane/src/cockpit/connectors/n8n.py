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

    def _webhooks(self) -> list[dict[str, Any]]:
        return list(self.runtime_config.get("webhooks", []))

    def list_tools(self) -> list[ToolManifest]:
        tools: list[ToolManifest] = []
        for hook in self._webhooks():
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
                    external_side_effects=not read_only,
                    supports_dry_run=bool(hook.get("supports_dry_run", False)),
                    idempotent=False,
                    timeout_seconds=int(hook.get("timeout_seconds", 60)),
                    retry=RetryPolicy(max_attempts=1),
                    approval="required" if not read_only else "auto",
                    undo_strategy=hook.get("undo_strategy", ""),
                )
            )
        return tools

    def get_tool(self, tool_id: str) -> ToolManifest | None:
        return next((t for t in self.list_tools() if t.id == tool_id), None)

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        hooks = self._webhooks()
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

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        name = tool_id.removeprefix("n8n.")
        hook = next((h for h in self._webhooks() if h["name"] == name), None)
        if hook is None:
            raise ConnectorError(f"n8n webhook “{name}” is not registered.")

        body = json.dumps(
            {
                "dry_run": ctx.dry_run,
                "payload": validated_input,
                "correlation_id": ctx.correlation_id,
            },
            ensure_ascii=False,
        ).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Cockpit-Idempotency-Key": hashlib.sha256(
                f"{ctx.run_id}|{tool_id}".encode()
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
            summary=f"n8n workflow “{name}” {'previewed (dry run)' if ctx.dry_run else 'executed'}",
            external_confirmed=not ctx.dry_run,
        )
