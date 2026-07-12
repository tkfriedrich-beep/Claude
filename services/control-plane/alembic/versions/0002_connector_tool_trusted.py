"""connector_tools.trusted column

Adds the trust flag distinguishing shipped-manifest tools (trusted) from runtime-registered
n8n/MCP tools (untrusted — always approval-gated). See DECISIONS ADR-014.

Revision ID: 0002_connector_tool_trusted
Revises: 0001_initial
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


revision: str = "0002_connector_tool_trusted"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001_initial runs create_all() from *current* model metadata (ADR-005), so a fresh DB
    # already has `trusted`; this delta only adds it to DBs created before the column existed.
    # Guarded so it's a no-op on fresh installs. SQLite supports ADD COLUMN natively (raw DDL
    # avoids a batch table-recreate that trips a spurious circular dependency on this table).
    if not _has_column("connector_tools", "trusted"):
        op.execute("ALTER TABLE connector_tools ADD COLUMN trusted BOOLEAN NOT NULL DEFAULT 1")


def downgrade() -> None:
    if _has_column("connector_tools", "trusted"):
        op.execute("ALTER TABLE connector_tools DROP COLUMN trusted")  # SQLite ≥ 3.35
