"""Test fixtures: isolated tmp data dir, fresh engine + schema per test, seeded workspace."""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text

import cockpit.config as config_module
import cockpit.db as db_module
import cockpit.events as events_module
import cockpit.registry as registry_module
from cockpit.models import Base

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
async def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict]:
    """Fresh settings/engine/schema/bus/registry per test."""
    data_dir = tmp_path / "local"
    monkeypatch.setenv("COCKPIT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("COCKPIT_START_BACKGROUND_TASKS", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_module.get_settings.cache_clear()
    settings = config_module.get_settings()

    await db_module.dispose_engine()
    engine = db_module.init_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts "
                "USING fts5(workspace_id, path, title, content)"
            )
        )
        # test schema mirrors a migrated deployment (doctor checks alembic_version)
        await conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        await conn.execute(
            text("INSERT OR IGNORE INTO alembic_version (version_num) VALUES ('0001_initial')")
        )
    events_module._bus = None
    registry_module.reset_registry()

    yield {"settings": settings, "tmp": tmp_path}

    await db_module.dispose_engine()
    config_module.get_settings.cache_clear()
    registry_module.reset_registry()
    events_module._bus = None


@pytest.fixture
async def workspace(app_env: dict) -> dict:
    """Onboarded demo workspace with a tmp copy of the ideas folder (writable in tests)."""
    ideas_dir = app_env["tmp"] / "bizideas"
    shutil.copytree(REPO_ROOT / "data" / "demo" / "bizideas", ideas_dir)

    from cockpit.api.system import onboarding
    from cockpit.db import db_session
    from cockpit.schemas import OnboardingRequest

    async with db_session() as session:
        result = await onboarding(
            OnboardingRequest(
                user_name="Testa",
                assistant_name="Otto",
                enable_demo_data=False,  # no seed runs in unit tests — keep them fast
                safe_mode=True,
                vault_path=str(REPO_ROOT / "data" / "demo" / "vault"),
                bizideas_path=str(ideas_dir),
            ),
            session,
        )
    return {**app_env, "workspace_id": result["workspace_id"], "ideas_dir": ideas_dir}


async def submit_and_process(workspace_id: str, **command) -> str:
    """Create a run via the API model then execute it inline (deterministic)."""
    from cockpit.db import db_session
    from cockpit.enums import RunStatus
    from cockpit.ids import correlation_id, new_id
    from cockpit.models import Run
    from cockpit.worker import process_run_inline

    async with db_session() as session:
        run = Run(
            id=new_id("run"),
            workspace_id=workspace_id,
            kind=command.get("kind", "skill"),
            status=RunStatus.QUEUED.value,
            title=command.get("title", "test run"),
            skill_slug=command.get("skill_slug"),
            command_text=command.get("text", ""),
            input=command.get("input", {}),
            mode=command.get("mode", "draft"),
            shadow=command.get("shadow", False),
            correlation_id=correlation_id(),
        )
        session.add(run)
        await session.commit()
        run_id = run.id
    await process_run_inline(run_id)
    return run_id


async def get_run(run_id: str):
    from cockpit.db import db_session
    from cockpit.models import Run

    async with db_session() as session:
        return await session.get(Run, run_id)
