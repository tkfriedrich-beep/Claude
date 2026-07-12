"""Application settings. Environment-driven; nothing here stores secrets."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    # services/control-plane/src/cockpit/config.py -> repo root is 4 levels up
    return Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COCKPIT_", env_file=".env", extra="ignore")

    data_dir: Path = _repo_root() / "data" / "local"
    demo_dir: Path = _repo_root() / "data" / "demo"
    skills_dir: Path = _repo_root() / "skills"
    connectors_dir: Path = _repo_root() / "connectors"

    port: int = 8787
    # localhost web app origins only (3100 = e2e test server)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3100",
        "http://127.0.0.1:3100",
    ]

    safe_mode_default: bool = True
    daily_budget_usd: float = 5.0
    run_budget_usd: float = 1.0
    approval_ttl_hours: int = 24
    worker_concurrency: int = 2
    worker_poll_seconds: float = 0.5
    scheduler_poll_seconds: float = 20.0
    run_timeout_default: int = 300
    max_steps_default: int = 25

    # Worker/scheduler are started by the FastAPI lifespan; tests turn this off.
    start_background_tasks: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cockpit.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def sync_database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
