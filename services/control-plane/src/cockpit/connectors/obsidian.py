"""Obsidian connector — a vault-aware local filesystem adapter (/raw, /wiki, /projects)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cockpit.connectors.base import (
    BaseConnector,
    ConnectorError,
    ExecutionContext,
    HealthStatus,
    ToolResult,
    contain_path,
)
from cockpit.connectors.local_files import MAX_READ_BYTES, LocalFilesConnector
from cockpit.enums import ConnectorHealthState

SECTIONS = ("raw", "wiki", "projects")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Tiny tolerant YAML-frontmatter reader (str values only — enough for note metadata)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip("\"'")
    return meta, text[end + 4 :]


class ObsidianConnector(BaseConnector):
    slug = "obsidian"

    def __init__(self, manifest_dir: Path) -> None:
        super().__init__(manifest_dir)
        self.runtime_config: dict[str, Any] = {}

    def _vault(self, ctx: ExecutionContext) -> Path:
        vault = (ctx.config or {}).get("vault_path") or self.runtime_config.get("vault_path")
        if not vault:
            raise ConnectorError("No Obsidian vault configured — set one in onboarding/settings.")
        return contain_path(vault, ctx.roots)

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        try:
            vault = self._vault(ctx)
        except ConnectorError as exc:
            return HealthStatus(ConnectorHealthState.DEGRADED, str(exc))
        if not vault.is_dir():
            return HealthStatus(ConnectorHealthState.UNAVAILABLE, f"Vault missing: {vault}")
        found = [s for s in SECTIONS if (vault / s).is_dir()]
        note_count = sum(1 for _ in vault.rglob("*.md"))
        return HealthStatus(
            ConnectorHealthState.OK,
            f"{note_count} notes; sections: {', '.join(found) or 'flat vault'}",
        )

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        vault = self._vault(ctx)
        match tool_id:
            case "obsidian.list_notes":
                return self._list_notes(vault, validated_input)
            case "obsidian.read_note":
                return self._read_note(vault, validated_input, ctx)
            case "obsidian.search_notes":
                return self._search(vault, validated_input)
            case "obsidian.recent_changes":
                return self._recent(vault, validated_input)
            case "obsidian.write_note":
                return self._write(vault, validated_input, ctx)
        raise ConnectorError(f"unknown tool {tool_id}")

    def _iter_notes(self, vault: Path, section: str) -> list[Path]:
        base = vault if section in ("", "all") else vault / section
        if not base.exists():
            return []
        return sorted(p for p in base.rglob("*.md") if not p.name.startswith("."))

    def _list_notes(self, vault: Path, inp: dict[str, Any]) -> ToolResult:
        notes = []
        for p in self._iter_notes(vault, inp.get("section", "all"))[:500]:
            stat = p.stat()
            text = p.read_bytes()[:4000].decode("utf-8", errors="replace")
            meta, _ = parse_frontmatter(text)
            notes.append(
                {
                    "path": str(p),
                    "rel_path": str(p.relative_to(vault)),
                    "title": meta.get("title") or p.stem,
                    "status": meta.get("status", ""),
                    "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    "size": stat.st_size,
                }
            )
        return ToolResult(
            ok=True,
            data={"notes": notes, "vault": str(vault)},
            summary=f"Listed {len(notes)} notes",
        )

    def _read_note(self, vault: Path, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        path = contain_path(
            vault / inp["path"] if not Path(inp["path"]).is_absolute() else inp["path"], ctx.roots
        )
        if not path.is_file():
            raise ConnectorError(f"Note not found: {inp['path']}")
        text = path.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        meta, body = parse_frontmatter(text)
        return ToolResult(
            ok=True,
            data={
                "path": str(path),
                "rel_path": str(path.relative_to(vault)),
                "frontmatter": meta,
                "content": body,
                "modified": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            },
            summary=f"Read note {path.stem}",
        )

    def _search(self, vault: Path, inp: dict[str, Any]) -> ToolResult:
        regex = re.compile(re.escape(inp["query"]), re.IGNORECASE)
        matches: list[dict[str, Any]] = []
        for p in self._iter_notes(vault, inp.get("section", "all")):
            if len(matches) >= 50:
                break
            text = p.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(
                        {
                            "rel_path": str(p.relative_to(vault)),
                            "line": i,
                            "text": line.strip()[:300],
                        }
                    )
                    if len(matches) >= 50:
                        break
        return ToolResult(
            ok=True,
            data={"matches": matches},
            summary=f"Found {len(matches)} match(es) in the vault",
        )

    def _recent(self, vault: Path, inp: dict[str, Any]) -> ToolResult:
        days = int(inp.get("days", 7))
        cutoff = datetime.now(UTC) - timedelta(days=days)
        changed = []
        for p in self._iter_notes(vault, inp.get("section", "all")):
            mtime = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            if mtime >= cutoff:
                changed.append(
                    {"rel_path": str(p.relative_to(vault)), "modified": mtime.isoformat()}
                )
        changed.sort(key=lambda c: str(c["modified"]), reverse=True)
        return ToolResult(
            ok=True,
            data={"changed": changed[:100], "days": days},
            summary=f"{len(changed)} note(s) changed in the last {days} days",
        )

    def _write(self, vault: Path, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        # Delegate write mechanics (diff, dry-run) to the local-files implementation.
        helper = LocalFilesConnector.__new__(LocalFilesConnector)
        target = vault / inp["path"] if not Path(inp["path"]).is_absolute() else Path(inp["path"])
        return helper._write({"path": str(target), "content": inp["content"]}, ctx)
