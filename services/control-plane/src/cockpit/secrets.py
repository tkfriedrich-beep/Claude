"""SecretStore abstraction.

Local web MVP: environment variables only. A future desktop wrapper swaps in an OS-keychain
implementation behind the same interface. Secrets are addressed by *name*; the value never
enters SQLite, run events, or logs (see logging.redact).
"""

from __future__ import annotations

import os
from typing import Protocol


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def exists(self, name: str) -> bool: ...


class EnvSecretStore:
    """Reads secrets from process environment (and services/control-plane/.env via pydantic)."""

    def get(self, name: str) -> str | None:
        value = os.environ.get(name)
        return value if value else None

    def exists(self, name: str) -> bool:
        return bool(os.environ.get(name))


_store: SecretStore = EnvSecretStore()


def get_secret_store() -> SecretStore:
    return _store
