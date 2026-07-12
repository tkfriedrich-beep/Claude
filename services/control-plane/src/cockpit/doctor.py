"""Doctor — diagnose environment/configuration; every failure prints its fix.

Runs as an API endpoint (GET /api/v1/doctor) and a CLI (`python -m cockpit.doctor`,
`make doctor`).
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import get_settings
from cockpit.models import Workspace
from cockpit.workspace import get_workspace_settings


def _check(name: str, ok: bool, detail: str, fix: str = "", warn: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok" if ok else ("warn" if warn else "fail"),
        "detail": detail,
        "fix": fix if not ok else "",
    }


async def run_checks(session: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    checks: list[dict[str, Any]] = []

    v = sys.version_info
    checks.append(
        _check(
            "Python ≥ 3.12",
            v >= (3, 12),
            f"{v.major}.{v.minor}.{v.micro}",
            "Install Python 3.12+ (e.g. `uv python install 3.12`).",
        )
    )
    checks.append(
        _check(
            "Node.js",
            shutil.which("node") is not None,
            shutil.which("node") or "not found",
            "Install Node 20+ (https://nodejs.org) for the web app.",
            warn=True,
        )
    )
    checks.append(
        _check(
            "pnpm",
            shutil.which("pnpm") is not None,
            shutil.which("pnpm") or "not found",
            "Run `corepack enable` or `npm i -g pnpm`.",
            warn=True,
        )
    )

    data_ok = os.access(settings.data_dir, os.W_OK)
    checks.append(
        _check(
            "Data directory writable",
            data_ok,
            str(settings.data_dir),
            f"Create it: mkdir -p {settings.data_dir}",
        )
    )

    try:
        await session.execute(text("SELECT 1"))
        version = await session.execute(text("SELECT version_num FROM alembic_version"))
        head = version.scalar()
        checks.append(
            _check(
                "Database migrated",
                head is not None,
                f"revision {head}" if head else "no alembic_version",
                "Run `make setup` (alembic upgrade head).",
            )
        )
    except Exception as exc:
        checks.append(
            _check("Database migrated", False, str(exc), "Run `make setup` (alembic upgrade head).")
        )

    workspace = await session.scalar(select(Workspace).limit(1))
    checks.append(
        _check(
            "Workspace onboarded",
            workspace is not None,
            workspace.name if workspace else "none",
            "Open http://localhost:3000 and complete onboarding, or run `make demo`.",
            warn=True,
        )
    )

    if workspace is not None:
        ws = await get_workspace_settings(session, workspace.id)
        from pathlib import Path

        if ws.vault_path:
            exists = Path(ws.vault_path).is_dir()
            checks.append(
                _check(
                    "Obsidian vault reachable",
                    exists,
                    ws.vault_path,
                    "Fix the path in Settings → Storage.",
                    warn=True,
                )
            )
        else:
            checks.append(
                _check(
                    "Obsidian vault configured",
                    False,
                    "not set",
                    "Set it in Settings → Storage (demo vault works too).",
                    warn=True,
                )
            )
        if ws.bizideas_path:
            exists = Path(ws.bizideas_path).is_dir()
            checks.append(
                _check(
                    "Ideas folder reachable",
                    exists,
                    ws.bizideas_path,
                    "Fix the path in Settings → Storage.",
                    warn=True,
                )
            )
        checks.append(
            _check(
                "Safe Mode",
                True,
                "ON — external writes blocked"
                if ws.safe_mode
                else "off — external writes possible after approval",
            )
        )

    from cockpit.runtime.claude import ClaudeAgentRuntime

    claude_ok, claude_detail = ClaudeAgentRuntime().available()
    checks.append(
        _check(
            "Claude provider",
            claude_ok,
            claude_detail,
            "Set ANTHROPIC_API_KEY in services/control-plane/.env or "
            "authenticate the `claude` CLI. Demo mode works without it.",
            warn=True,
        )
    )

    failures = [c for c in checks if c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "status": "fail" if failures else ("warn" if warnings else "ok"),
        "checks": checks,
        "summary": f"{len(failures)} failure(s), {len(warnings)} warning(s), "
        f"{len(checks) - len(failures) - len(warnings)} ok",
    }


async def _main() -> int:
    from cockpit.db import apply_sqlite_pragmas, db_session, init_engine

    settings = get_settings()
    engine = init_engine(settings)
    await apply_sqlite_pragmas(engine)
    async with db_session() as session:
        report = await run_checks(session)
    icons = {"ok": "✅", "warn": "🟡", "fail": "❌"}
    print("AgenticOS Cockpit — doctor\n")
    for check in report["checks"]:
        print(f"{icons[check['status']]} {check['name']}: {check['detail']}")
        if check["fix"]:
            print(f"   ↳ fix: {check['fix']}")
    print(f"\n{report['summary']}")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(_main()))
