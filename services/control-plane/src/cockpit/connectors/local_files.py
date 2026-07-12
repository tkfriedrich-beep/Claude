"""Local Files connector — bounded roots, safe reads, approval-gated writes."""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cockpit.connectors.base import (
    BaseConnector,
    ConnectorError,
    ExecutionContext,
    HealthStatus,
    PreviewNotSupported,
    ToolResult,
    contain_path,
    contain_write_target,
    is_within_roots,
    open_contained_write,
    relparts_under_roots,
    safe_glob_pattern,
)
from cockpit.enums import ConnectorHealthState

TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}
MAX_READ_BYTES = 512_000
MAX_LIST = 500
MAX_MATCHES = 60


def _rel(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            return str(path.relative_to(root.resolve()))
        except ValueError:
            continue
    return str(path)


def _unified_diff(old_content: str, new_content: str, name: str) -> str:
    return (
        "\n".join(
            difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
                lineterm="",
            )
        )
        or "(new file)"
    )


class LocalFilesConnector(BaseConnector):
    slug = "local-files"

    async def health_check(self, ctx: ExecutionContext) -> HealthStatus:
        readable = [r for r in ctx.roots if r.exists()]
        if not readable:
            return HealthStatus(ConnectorHealthState.UNAVAILABLE, "No readable roots configured")
        return HealthStatus(
            ConnectorHealthState.OK, f"{len(readable)} root(s): " + ", ".join(map(str, readable))
        )

    async def execute(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        match tool_id:
            case "local_files.list":
                return self._list(validated_input, ctx)
            case "local_files.read":
                return self._read(validated_input, ctx)
            case "local_files.search":
                return self._search(validated_input, ctx)
            case "local_files.write":
                return self._write(validated_input, ctx)
        raise ConnectorError(f"unknown tool {tool_id}")

    async def preview(
        self, tool_id: str, validated_input: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        if tool_id == "local_files.write":
            return self._preview_write(validated_input, ctx)
        raise PreviewNotSupported(f"{tool_id} has no preview")

    def _list(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        root = contain_path(inp.get("root") or str(ctx.roots[0]), ctx.roots)
        pattern = safe_glob_pattern(inp.get("glob", "**/*"))
        entries: list[dict[str, Any]] = []
        if root.is_dir():
            for p in sorted(root.glob(pattern)):
                # Re-check each discovered path: a symlinked entry inside the root, or a `..`
                # that slipped through, must not leak an outside file (review R2-F4).
                if p.is_symlink() or not is_within_roots(p, ctx.roots):
                    continue
                if p.is_file() and not p.name.startswith("."):
                    stat = p.stat()
                    entries.append(
                        {
                            "path": str(p),
                            "rel_path": _rel(p, ctx.roots),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        }
                    )
                if len(entries) >= MAX_LIST:
                    break
        return ToolResult(
            ok=True,
            data={"entries": entries, "truncated": len(entries) >= MAX_LIST},
            summary=f"Listed {len(entries)} file(s) in {root.name}",
        )

    def _read(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        path = contain_path(inp["path"], ctx.roots)
        if not path.is_file():
            raise ConnectorError(f"File not found: {inp['path']}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise ConnectorError(f"Unsupported file type “{path.suffix}” — text files only.")
        content = path.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        stat = path.stat()
        return ToolResult(
            ok=True,
            data={
                "path": str(path),
                "content": content,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                "truncated": stat.st_size > MAX_READ_BYTES,
            },
            summary=f"Read {path.name}",
        )

    def _search(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        query = inp["query"]
        root = contain_path(inp.get("root") or str(ctx.roots[0]), ctx.roots)
        regex = re.compile(re.escape(query), re.IGNORECASE)
        matches: list[dict[str, Any]] = []
        candidates = root.rglob("*") if root.is_dir() else [root]
        for p in candidates:
            if len(matches) >= MAX_MATCHES:
                break
            # Never follow a symlinked entry out of the roots (review R2-F4).
            if p.is_symlink() or not is_within_roots(p, ctx.roots):
                continue
            if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = p.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(
                        {
                            "path": str(p),
                            "rel_path": _rel(p, ctx.roots),
                            "line": i,
                            "text": line.strip()[:300],
                        }
                    )
                    if len(matches) >= MAX_MATCHES:
                        break
        return ToolResult(
            ok=True,
            data={"matches": matches, "truncated": len(matches) >= MAX_MATCHES},
            summary=f"Found {len(matches)} match(es) for “{query}”",
        )

    def _resolve_write(self, inp: dict[str, Any], ctx: ExecutionContext):
        # Containment must hold for the *resolved* target — including not-yet-existing files
        # and a symlinked final component that would escape the roots (review F2).
        path = contain_write_target(inp["path"], ctx.roots)
        if fnmatch.fnmatch(path.name, ".*"):
            raise ConnectorError("Refusing to write hidden files.")
        new_content: str = inp["content"]
        old_content = ""
        if path.exists():
            old_content = path.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        diff = (
            "\n".join(
                difflib.unified_diff(
                    old_content.splitlines(),
                    new_content.splitlines(),
                    fromfile=f"a/{path.name}",
                    tofile=f"b/{path.name}",
                    lineterm="",
                )
            )
            or "(new file)"
        )
        return path, new_content, diff

    def _preview_write(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        path, new_content, diff = self._resolve_write(inp, ctx)
        return ToolResult(
            ok=True,
            data={"path": str(path), "written": False, "diff": diff, "bytes": len(new_content)},
            summary=f"Preview: would write {len(new_content)} bytes to {path.name}",
        )

    def _write(self, inp: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        assert not ctx.dry_run, "real write called for a dry-run — gateway routing bug"
        raw = Path(inp["path"]).expanduser()
        if fnmatch.fnmatch(raw.name, ".*"):
            raise ConnectorError("Refusing to write hidden files.")
        # Containment is enforced by DESCENT, not just a pre-check: resolve the logical path under
        # a root (no symlink following), then open it component-by-component with O_NOFOLLOW from a
        # root dir fd. A parent directory swapped to a symlink after this point is rejected at open
        # time rather than followed out of the workspace (review R3-F3). st_nlink is checked before
        # truncating so a rejected write does no damage (review R2-F3).
        root, rel_parts = relparts_under_roots(raw, ctx.roots)
        new_content: str = inp["content"]
        data = new_content.encode("utf-8")
        fd = open_contained_write(root, rel_parts)
        try:
            if os.fstat(fd).st_nlink > 1:
                raise ConnectorError(
                    "Refusing to write a hardlinked file — it may share an inode with a "
                    "file outside the workspace."
                )
            old_content = os.read(fd, MAX_READ_BYTES).decode("utf-8", errors="replace")
            diff = _unified_diff(old_content, new_content, raw.name)
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, data)
        finally:
            os.close(fd)
        return ToolResult(
            ok=True,
            data={"path": str(raw), "written": True, "diff": diff, "bytes": len(new_content)},
            summary=f"Wrote {raw.name} ({len(new_content)} bytes)",
            external_confirmed=True,  # filesystem write verified by the write call itself
        )
