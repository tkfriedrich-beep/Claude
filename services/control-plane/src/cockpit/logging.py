"""Structured JSON logging with secret redaction.

Redaction is defense-in-depth: secrets should never reach a log call in the first place
(SecretStore hands out values only at the call site), but any string that *looks* like a
credential is masked before emission, and known-sensitive keys are masked recursively.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any

SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|authorization|credential|cookie)", re.IGNORECASE
)
# sk-ant-..., ghp_..., xoxb-..., AWS keys, long hex/base64 blobs, bearer headers
SENSITIVE_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|xox[bap]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{16,})"
)
# Credentials embedded in a URL's userinfo (scheme://user:password@host) — regexes above key off
# credential *shape* and miss an arbitrary password, so a `web.fetch` URL could persist one
# (review R3-F5). Mask the whole userinfo, keeping scheme + host for audit legibility.
URL_USERINFO_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@")

MASK = "•••redacted•••"


def redact_text(text: str) -> str:
    text = URL_USERINFO_RE.sub(r"\1" + MASK + "@", text)
    return SENSITIVE_VALUE_RE.sub(MASK, text)


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Recursively mask sensitive keys and credential-shaped values."""
    if _depth > 8:
        return "…"
    if isinstance(value, dict):
        return {
            k: (MASK if SENSITIVE_KEY_RE.search(str(k)) else redact(v, _depth=_depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, _depth=_depth + 1) for v in value[:200]]
    if isinstance(value, str):
        return redact_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        for key in ("correlation_id", "run_id", "tool_id", "connector_id", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(redact(payload), ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
