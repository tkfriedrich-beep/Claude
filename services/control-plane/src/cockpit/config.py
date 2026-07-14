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
    # Additive: also allow same-machine access over a private Tailscale tailnet, so you can
    # open the cockpit on your phone. Matches loopback, Tailscale CGNAT IPs (100.64.0.0/10),
    # and MagicDNS *.ts.net names — nothing public. Inert unless the server is actually bound
    # to a reachable interface (see `make phone`). Set COCKPIT_CORS_ORIGIN_REGEX="" to disable.
    cors_origin_regex: str | None = (
        r"^https?://("
        r"localhost|127\.0\.0\.1|\[::1\]"
        r"|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"  # Tailscale 100.64.0.0/10
        r"|([a-zA-Z0-9-]+\.)+ts\.net"  # Tailscale MagicDNS names
        r")(:\d+)?$"
    )
    # Network access guard (see cockpit/netguard.py). Loopback is always allowed; these
    # comma-separated CIDRs are the ONLY other clients that may reach the (unauthenticated)
    # API when the socket is bound to a reachable interface (`make phone`). Default = the
    # Tailscale CGNAT range, so a random LAN host cannot hit the API even though CORS would
    # let a browser through. Set COCKPIT_TRUSTED_NETWORKS="0.0.0.0/0,::/0" to allow all
    # (opt-in, e.g. a trusted LAN), or "" to allow loopback only.
    trusted_networks: str = "100.64.0.0/10"

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
