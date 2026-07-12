"""ID helpers: prefixed, sortable-enough identifiers for a local system."""

from __future__ import annotations

import time
import uuid


def new_id(prefix: str) -> str:
    # time prefix keeps ids roughly sortable for humans; uuid4 guarantees uniqueness
    return f"{prefix}_{int(time.time() * 1000):x}{uuid.uuid4().hex[:12]}"


def correlation_id() -> str:
    return f"cor_{uuid.uuid4().hex[:16]}"
