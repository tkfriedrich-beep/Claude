"""Common connector contract (BUILD_BRIEF §Connector architecture).

Connectors expose tools; they never decide policy. The gateway validates schemas, applies
policy, handles approvals/idempotency/timeouts/retries, and calls Connector.execute() last.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
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
    # Tools declared in a shipped connector manifest are trusted code. Tools whose
    # classification is supplied at runtime registration (n8n webhooks, discovered MCP
    # tools) set this False so the policy never auto-runs them on their own say-so.
    trusted: bool = True


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


class PreviewNotSupported(ConnectorError):
    """Raised when a dry-run/preview is requested for a tool that has no preview method."""


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

    def list_tools(self, config: dict[str, Any] | None = None) -> list[ToolManifest]:
        # `config` lets the gateway resolve a tool manifest from a *specific workspace's* connector
        # config instead of the process-global singleton (review R3-F2). Static connectors ignore
        # it (their manifest is code-defined); dynamic connectors (n8n/mcp) override this.
        return list(self._manifest.tools)

    def get_tool(self, tool_id: str, config: dict[str, Any] | None = None) -> ToolManifest | None:
        return next((t for t in self.list_tools(config) if t.id == tool_id), None)

    def owns_tool(self, tool_id: str) -> bool:
        """True if this connector defines `tool_id` — used to pick the connector *before* a
        workspace config is loaded. Config-independent so it can't be spoofed by another
        workspace's singleton state (review R3-F2)."""
        return self.get_tool(tool_id) is not None

    @abstractmethod
    async def health_check(self, ctx: ExecutionContext) -> HealthStatus: ...

    @abstractmethod
    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        """Perform the tool's REAL effect. Never called for a dry-run (the gateway routes
        previews to preview()). Implementations may assert `not ctx.dry_run`."""

    async def preview(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        """Produce a side-effect-free preview (diff / would-do) of a tool.

        Default: refuse. Dry-run is a distinct capability, not a boolean passed to the same
        executor — so a connector that hasn't *deliberately* written a preview can never
        accidentally perform the real effect when the gateway asks for a preview. Only
        connectors that override this may declare `supports_dry_run: true`.
        """
        raise PreviewNotSupported(
            f"Tool “{tool_id}” has no dry-run preview — it cannot run in draft/shadow mode."
        )

    def supports_preview(self) -> bool:
        """True if this connector overrides preview() (used to validate manifests at load)."""
        return type(self).preview is not BaseConnector.preview

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


def is_within_roots(path: Path, roots: list[Path]) -> bool:
    """True if `path` (symlinks resolved) lives under an allowed root. Never raises.

    Use this to re-check every path discovered by glob/rglob before stat/read — the starting
    root being contained does not make a *symlinked entry inside it* contained (review R2-F4).
    """
    try:
        final = Path(os.path.realpath(path))
    except OSError:
        return False
    for root in roots:
        try:
            final.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def safe_glob_pattern(pattern: str) -> str:
    """Reject glob patterns that escape the starting directory (`..`, absolute) — R2-F4."""
    parts = PurePosixPath(pattern).parts
    if pattern.startswith("/") or ".." in parts or ".." in pattern.split("\\"):
        raise ConnectorError(f"Unsafe glob pattern “{pattern}” — no absolute paths or “..”.")
    return pattern


def relparts_under_roots(candidate: str | Path, roots: list[Path]) -> tuple[Path, list[str]]:
    """Return (resolved_root, relative-parts) for a *logical* path under a root, without following
    any symlink in the candidate. Rejects `..` and paths outside every root. Raises ConnectorError.

    Unlike `contain_write_target` (which realpath-resolves the parent), this keeps the path
    logical so the caller can walk it component-by-component with O_NOFOLLOW (review R3-F3)."""
    raw = Path(candidate).expanduser()
    if ".." in raw.parts:
        raise ConnectorError(f"Refusing a path containing “..” — “{candidate}”.")
    for root in roots:
        root_abs = root.resolve()  # resolving the trusted root itself is fine
        base = raw if raw.is_absolute() else root_abs / raw
        try:
            rel = Path(os.path.normpath(base)).relative_to(root_abs)
        except ValueError:
            continue
        if ".." in rel.parts or rel == Path("."):
            continue
        return root_abs, list(rel.parts)
    raise ConnectorError(
        f"Path “{candidate}” is outside the configured roots — refusing to touch it."
    )


def open_contained_write(root: Path, rel_parts: list[str]) -> int:
    """Open `root/<rel_parts>` for read+write, descending from a root dir fd with O_NOFOLLOW on
    EVERY component. A symlink swapped into any parent between validation and open (a TOCTOU race)
    is rejected at open time, not followed — closing the parent-symlink escape (review R3-F3).

    Returns a file descriptor the caller must close. Missing intermediate directories are created
    safely via mkdirat. Raises ConnectorError on any symlink/He escape or bad component."""
    o_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    dir_fd = os.open(root, o_dir)  # root itself is trusted config
    try:
        for part in rel_parts[:-1]:
            if part in ("", ".", ".."):
                raise ConnectorError(f"Refusing unsafe path component “{part}”.")
            try:
                nxt = os.open(part, o_dir | os.O_NOFOLLOW, dir_fd=dir_fd)
            except FileNotFoundError:
                os.mkdir(part, 0o755, dir_fd=dir_fd)
                nxt = os.open(part, o_dir | os.O_NOFOLLOW, dir_fd=dir_fd)
            except OSError as exc:
                raise ConnectorError(
                    f"Refusing to descend through “{part}” ({exc.strerror or exc}) — "
                    "it may be a symlink out of the workspace."
                ) from exc
            os.close(dir_fd)
            dir_fd = nxt
        name = rel_parts[-1]
        if name in ("", ".", ".."):
            raise ConnectorError(f"Refusing to write to “{name}” — invalid file name.")
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            return os.open(name, flags, 0o644, dir_fd=dir_fd)
        except OSError as exc:
            raise ConnectorError(
                f"Refusing to write “{name}” ({exc.strerror or exc}) — it may be a symlink "
                "out of the workspace."
            ) from exc
    finally:
        os.close(dir_fd)


def contain_write_target(candidate: str | Path, roots: list[Path]) -> Path:
    """Resolve a *write* target and require it stays under a root — following symlinks.

    `contain_path` is enough for reads (it resolves the whole path), but for writes the
    caller must also refuse a symlinked final component that points outside a root
    (`os.path.realpath` resolves symlinks even for a not-yet-existing tail). This closes the
    "write through a symlink escapes the workspace" hole (review F2).
    """
    raw = Path(candidate).expanduser()
    name = raw.name
    if name in ("", ".", ".."):
        raise ConnectorError(f"Refusing to write to “{candidate}” — invalid file name.")
    # Parent must itself be inside a root (resolving any symlinks along the way).
    parent = contain_path(raw.parent, roots)
    target = parent / name
    if target.is_symlink():
        raise ConnectorError(
            f"Refusing to write through the symlink “{candidate}” — it may point outside "
            "the workspace."
        )
    # realpath resolves symlinks (incl. a symlinked tail / parent) and normalizes `..`;
    # the fully-resolved location must remain within a root.
    final = Path(os.path.realpath(target))
    for root in roots:
        try:
            final.relative_to(root.resolve())
            return target
        except ValueError:
            continue
    raise ConnectorError(
        f"Path “{candidate}” resolves outside the configured roots — refusing to write it."
    )
