"""Common connector contract (BUILD_BRIEF §Connector architecture).

Connectors expose tools; they never decide policy. The gateway validates schemas, applies
policy, handles approvals/idempotency/timeouts/retries, and calls Connector.execute() last.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from cockpit.enums import ConnectorHealthState, ConnectorMode, RiskLevel, ToolAccess
from cockpit.logging import redact


class RetryPolicy(BaseModel):
    max_attempts: int = 1
    backoff_seconds: float = 1.0


class ToolManifest(BaseModel):
    id: str
    version: str = "1"
    connector: str = ""
    name: str = ""
    description: str = ""
    capability: str = ""
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    access: ToolAccess = ToolAccess.READ
    risk_level: RiskLevel = RiskLevel.R0
    sensitivity: str = "normal"
    required_scopes: list[str] = Field(default_factory=list)
    external_side_effects: bool = False
    supports_dry_run: bool = False
    idempotent: bool = True
    timeout_seconds: int = 30
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    approval: str = "auto"  # auto | required | forbidden
    undo_strategy: str = ""


class ConnectorManifest(BaseModel):
    id: str
    name: str
    version: str = "0.1.0"
    category: str = "local"
    description: str = ""
    auth_type: str = "none"
    capabilities: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    data_sensitivity: str = "normal"
    default_mode: ConnectorMode = ConnectorMode.READ_ONLY
    mock: bool = False
    tools: list[ToolManifest] = Field(default_factory=list)


@dataclass
class HealthStatus:
    state: ConnectorHealthState
    detail: str = ""


@dataclass
class ExecutionContext:
    workspace_id: str
    run_id: str
    correlation_id: str
    dry_run: bool = False
    roots: list[Path] = field(default_factory=list)  # allowed filesystem roots
    config: dict[str, Any] = field(default_factory=dict)  # connector row config (non-secret)
    settings: Any = None  # cockpit.config.Settings


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""  # one human-readable line for the timeline
    external_confirmed: bool = False  # True only when the external system confirmed the effect
    error: str | None = None


class ConnectorError(Exception):
    """Raised by connectors for expected failures (unreachable, bad path, upstream error)."""


class BaseConnector(ABC):
    """Loads its manifest from <repo>/connectors/<slug>/manifest.yaml."""

    slug: str = ""

    def __init__(self, manifest_dir: Path) -> None:
        self._manifest = self._load_manifest(manifest_dir / self.slug / "manifest.yaml")

    def _load_manifest(self, path: Path) -> ConnectorManifest:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        tools = [ToolManifest(connector=raw["id"], **t) for t in raw.pop("tools", [])]
        return ConnectorManifest(**raw, tools=tools)

    def get_manifest(self) -> ConnectorManifest:
        return self._manifest

    def list_tools(self) -> list[ToolManifest]:
        return list(self._manifest.tools)

    def get_tool(self, tool_id: str) -> ToolManifest | None:
        return next((t for t in self._manifest.tools if t.id == tool_id), None)

    @abstractmethod
    async def health_check(self, ctx: ExecutionContext) -> HealthStatus: ...

    @abstractmethod
    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult: ...

    def normalize_result(self, raw: Any) -> dict[str, Any]:
        return raw if isinstance(raw, dict) else {"value": raw}

    def redact_for_log(self, data: dict[str, Any]) -> dict[str, Any]:
        return redact(data)


def contain_path(candidate: str | Path, roots: list[Path]) -> Path:
    """Resolve a path and require it to live under one of the allowed roots."""
    resolved = Path(candidate).expanduser().resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ConnectorError(
        f"Path “{candidate}” is outside the configured roots — refusing to touch it."
    )
