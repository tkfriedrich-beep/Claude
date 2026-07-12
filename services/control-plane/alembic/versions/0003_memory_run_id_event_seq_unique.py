"""memories.run_id + unique (run_id, seq) on run_events

Adds the run that proposed each memory (idempotent result persistence across crash/resume —
review R2-F10) and enforces one sequence number per run for events so a lock-eviction race can
never assign a duplicate (review R2-F12). See DECISIONS ADR-015.

Revision ID: 0003_memory_run_id_event_seq_unique
Revises: 0002_connector_tool_trusted
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def _has_unique(table: str, cols: list[str]) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    target = list(cols)
    for ix in insp.get_indexes(table):
        if ix.get("unique") and list(ix.get("column_names") or []) == target:
            return True
    for uc in insp.get_unique_constraints(table):
        if list(uc.get("column_names") or []) == target:
            return True
    return False


revision: str = "0003_memory_run_id_event_seq_unique"
down_revision: str | None = "0002_connector_tool_trusted"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001_initial runs create_all() from *current* model metadata (ADR-005), so a fresh DB
    # already has both of these; these deltas only patch DBs created before they existed. Both
    # guarded so they're no-ops on fresh installs.
    if not _has_column("memories", "run_id"):
        op.execute("ALTER TABLE memories ADD COLUMN run_id VARCHAR(64)")
        # index mirrors the model's index=True (harmless if a fresh DB already made it).
        op.execute("CREATE INDEX IF NOT EXISTS ix_memories_run_id ON memories (run_id)")
    # A fresh DB gets UNIQUE(run_id, seq) inline via create_all (SQLite backs it with an
    # autoindex), so _has_unique short-circuits; only an older DB needs this named index.
    if not _has_unique("run_events", ["run_id", "seq"]):
        # A legacy 0002 DB may hold duplicate (run_id, seq) rows — exactly the state the pre-fix
        # event race produced, i.e. the DBs that most need this migration. Creating the unique
        # index directly would raise "UNIQUE constraint failed" and brick the upgrade
        # (review R3-F11). Renumber the affected runs' events gap-free in stable (seq, id) order
        # first, so every row becomes unique while preserving order, then build the index.
        op.execute(
            """
            WITH renum AS (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY seq, id) AS rn
                FROM run_events
                WHERE run_id IN (
                    SELECT run_id FROM run_events GROUP BY run_id, seq HAVING COUNT(*) > 1
                )
            )
            UPDATE run_events
               SET seq = (SELECT rn FROM renum WHERE renum.id = run_events.id)
             WHERE id IN (SELECT id FROM renum)
            """
        )
        op.execute("CREATE UNIQUE INDEX uq_run_events_run_seq ON run_events (run_id, seq)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_run_events_run_seq")
    if _has_column("memories", "run_id"):
        op.execute("DROP INDEX IF EXISTS ix_memories_run_id")
        op.execute("ALTER TABLE memories DROP COLUMN run_id")  # SQLite ≥ 3.35
