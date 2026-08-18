"""Alembic environment configuration — async SQLite support.

This env.py uses an async engine because the project's persistence layer
is built on ``sqlalchemy.ext.asyncio``.  Alembic's ``run_async()`` wrapper
handles the async connection lifecycle.

Target metadata is loaded from ``backend.app.persistence.models.Base.metadata``.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Alembic Config object
config = context.config

# Set up loggers
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Target metadata ───────────────────────────────────────────────────────
from backend.app.persistence.models import Base

target_metadata = Base.metadata


# ── Offline ────────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configuration is read from ``alembic.ini``'s ``sqlalchemy.url``.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online (async) ─────────────────────────────────────────────────────────


def do_run_migrations(connection):
    """Synchronous migration runner, called with a sync connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within a connection."""
    # Read the database URL from alembic.ini; fall back to a default SQLite URL
    db_url = config.get_main_option("sqlalchemy.url", "sqlite+aiosqlite:///")

    connectable = create_async_engine(db_url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    asyncio.run(run_async_migrations())


# ── Dispatch ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()