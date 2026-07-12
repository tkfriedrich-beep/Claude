from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from cockpit.config import get_settings
from cockpit.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # SQLite FTS5 creates internal shadow tables (knowledge_fts, _data, _idx, _docsize,
    # _content, _config). They aren't in our metadata; never let autogenerate drop them.
    if type_ == "table" and (name == "knowledge_fts" or name.startswith("knowledge_fts_")):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    engine = create_engine(settings.sync_database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite needs batch mode for ALTERs
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
