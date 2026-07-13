"""Workspace settings access — operational switches live on the workspace row (no secrets)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cockpit.config import get_settings
from cockpit.models import Workspace


@dataclass
class WorkspaceSettings:
    workspace_id: str
    safe_mode: bool = True
    kill_switch: bool = False
    demo_mode: bool = False
    vault_path: str | None = None
    bizideas_path: str | None = None
    default_mode: str = "draft"
    provider: str = "mock"
    model: str = ""
    theme: str = "system"
    daily_budget_usd: float = 5.0
    run_budget_usd: float = 1.0
    raw: dict[str, Any] = field(default_factory=dict)


async def get_default_workspace(session: AsyncSession) -> Workspace | None:
    return await session.scalar(select(Workspace).order_by(Workspace.created_at).limit(1))


async def get_workspace_settings(session: AsyncSession, workspace_id: str) -> WorkspaceSettings:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise ValueError(f"workspace {workspace_id} not found")
    s = ws.settings or {}
    app = get_settings()
    return WorkspaceSettings(
        workspace_id=workspace_id,
        safe_mode=bool(s.get("safe_mode", app.safe_mode_default)),
        kill_switch=bool(s.get("kill_switch", False)),
        demo_mode=bool(s.get("demo_mode", False)),
        vault_path=s.get("vault_path"),
        bizideas_path=s.get("bizideas_path"),
        default_mode=s.get("default_mode", "draft"),
        provider=s.get("provider", "mock"),
        model=s.get("model", ""),
        theme=s.get("theme", "system"),
        daily_budget_usd=float(s.get("daily_budget_usd", app.daily_budget_usd)),
        run_budget_usd=float(s.get("run_budget_usd", app.run_budget_usd)),
        raw=dict(s),
    )


async def update_workspace_settings(
    session: AsyncSession, workspace_id: str, patch: dict[str, Any]
) -> WorkspaceSettings:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise ValueError(f"workspace {workspace_id} not found")
    merged = dict(ws.settings or {})
    merged.update({k: v for k, v in patch.items() if v is not None})
    ws.settings = merged
    await session.flush()
    return await get_workspace_settings(session, workspace_id)


async def allowed_roots_for(workspace_id: str) -> list[Path]:
    """Filesystem roots tools may touch: local data, demo data, configured vault + ideas."""
    from cockpit.db import db_session

    app = get_settings()
    roots: list[Path] = [app.data_dir, app.demo_dir]
    async with db_session() as session:
        try:
            ws = await get_workspace_settings(session, workspace_id)
        except ValueError:
            return roots
    for p in (ws.vault_path, ws.bizideas_path):
        if p:
            path = Path(p).expanduser()
            if path.exists():
                roots.append(path.resolve())
    return roots
