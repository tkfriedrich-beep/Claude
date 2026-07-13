"""SecretStore abstraction.

Secrets are addressed by *name*; the value never enters SQLite, run events, or logs
(see logging.redact). Two implementations share one interface:

- ``EnvSecretStore`` — read-only view of the process environment. Used by tests and by any
  deployment that injects secrets purely through env vars.
- ``LocalSecretStore`` — the default for the local desktop MVP. Reads prefer the process
  environment (a value exported in your shell always wins), then fall back to a gitignored
  ``data/local/secrets.env`` file (mode 0600). Writes go to that file only, so keys entered
  in the UI survive restarts without ever touching the database.

A future desktop wrapper can swap in an OS-keychain implementation behind the same interface.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

# Env-var style: uppercase, digits, underscores; must start with a letter. Matches
# ANTHROPIC_API_KEY, OPENAI_API_KEY, FIRECRAWL_API_KEY, COCKPIT_N8N_SECRET_MYFLOW, …
SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,96}$")

SecretSource = Literal["env", "file", "none"]


class InvalidSecretName(ValueError):
    """Raised when a proposed secret name is not a safe env-var-style identifier."""


def validate_secret_name(name: str) -> str:
    if not SECRET_NAME_RE.match(name or ""):
        raise InvalidSecretName(
            f"“{name}” is not a valid secret name. Use UPPER_SNAKE_CASE letters, digits and "
            "underscores, starting with a letter (e.g. OPENAI_API_KEY)."
        )
    return name


@runtime_checkable
class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def exists(self, name: str) -> bool: ...


@runtime_checkable
class MutableSecretStore(SecretStore, Protocol):
    """A store the settings UI can manage: list configured names and set/delete values."""

    def list_names(self) -> list[str]: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> bool: ...
    def source_of(self, name: str) -> SecretSource: ...


class EnvSecretStore:
    """Reads secrets from the process environment (and control-plane/.env via the shell)."""

    def get(self, name: str) -> str | None:
        value = os.environ.get(name)
        return value if value else None

    def exists(self, name: str) -> bool:
        return bool(os.environ.get(name))


class LocalSecretStore:
    """File-backed store for the local MVP. Env wins over file for reads; writes hit the file.

    The file is a minimal ``KEY=VALUE`` env file (one per line). It is created lazily with
    owner-only permissions (0600) and lives under ``data/local`` which is already gitignored;
    an extra ``.gitignore`` guard for ``secrets.env`` is added defensively.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        if self._path is not None:
            return self._path
        # Imported lazily so tests that swap COCKPIT_DATA_DIR are honoured.
        from cockpit.config import get_settings

        return get_settings().data_dir / "secrets.env"

    # ---- reads -------------------------------------------------------------
    def _read_file(self) -> dict[str, str]:
        path = self.path
        if not path.exists():
            return {}
        out: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if SECRET_NAME_RE.match(key):
                out[key] = value.strip()
        return out

    def get(self, name: str) -> str | None:
        env = os.environ.get(name)
        if env:
            return env
        value = self._read_file().get(name)
        return value or None

    def exists(self, name: str) -> bool:
        return bool(self.get(name))

    def source_of(self, name: str) -> SecretSource:
        if os.environ.get(name):
            return "env"
        if self._read_file().get(name):
            return "file"
        return "none"

    def list_names(self) -> list[str]:
        """Names the UI manages (file-backed). Env-injected secrets are intentionally not
        enumerated here — they are reported per-slot via ``exists``/``source_of`` instead."""
        return sorted(self._read_file())

    # ---- writes ------------------------------------------------------------
    def set(self, name: str, value: str) -> None:
        validate_secret_name(name)
        if "\n" in value or "\r" in value:
            raise InvalidSecretName("Secret values cannot contain newlines.")
        data = self._read_file()
        data[name] = value.strip()
        self._write_file(data)

    def delete(self, name: str) -> bool:
        data = self._read_file()
        if name not in data:
            return False
        del data[name]
        self._write_file(data)
        return True

    def _write_file(self, data: dict[str, str]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            "# AgenticOS Cockpit local secrets — gitignored, mode 0600. Never commit this file.\n"
            "# Managed via Integrations → Secrets. Values set in the shell env override these.\n"
            + "".join(f"{k}={data[k]}\n" for k in sorted(data))
        )
        # Atomic replace so a crash mid-write can't corrupt the file; 0600 from creation.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".secrets.", suffix=".tmp")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)


_store: MutableSecretStore = LocalSecretStore()


def get_secret_store() -> MutableSecretStore:
    return _store
