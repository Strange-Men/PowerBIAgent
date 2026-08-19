"""Persistence layer — SQLAlchemy Async engine, session factory, and lifecycle.

M4.0 Core Design
================

Responsibilities
----------------
*   Create and manage the AsyncEngine and async_sessionmaker.
*   Construct the deterministic SQLite URL from Settings.
*   Apply SQLite PRAGMAs (foreign_keys=ON, journal_mode=WAL, busy_timeout).
*   Provide startup / shutdown helpers for the FastAPI lifespan.

Boundaries
----------
*   This module owns the engine/session lifecycle but NOT the repository instances.
*   Repository lifecycle is managed at the application wiring layer (``main.py``).
*   TurnPipeline never receives a raw SQLAlchemy Session — it depends on ``MemoryRepository`` / ``SnapshotRepository`` ABCs.

Usage
-----
    from backend.app.config.settings import Settings, PersistenceBackend
    from backend.app.persistence.database import create_engine, dispose_engine, create_session_factory

    settings = get_settings()
    if settings.is_persistence_sqlite:
        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        # ...
        await dispose_engine(engine)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config.settings import Settings

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_sqlite_url(settings: Settings) -> str:
    """Build a deterministic ``sqlite+aiosqlite:///...`` URL.

    The database directory is created if it does not exist.
    The URL always uses a POSIX-style path (forward slashes).
    """
    db_path = Path(settings.persistence_database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Use resolve() to get an absolute POSIX-style path
    posix = db_path.resolve().as_posix()
    return f"sqlite+aiosqlite:///{posix}"


def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Apply per-connection SQLite PRAGMAs.

    Called once per new DBAPI connection via the ``PoolEvents.connect``
    event (registered through SQLAlchemy's ``event.listen``).

    Per-connection PRAGMAs (applied to *every* new connection):
    * ``foreign_keys = ON``  — FK enforcement is per-connection in SQLite
    * ``busy_timeout = 5000`` — 5 second busy wait, bounded

    Database-level PRAGMAs (persistent once set; do NOT go here):
    * ``journal_mode = WAL`` — database-level, survives connection close.
      Applied once by ``configure_engine()`` during startup.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.close()


def create_engine(
    settings: Settings,
    *,
    echo: bool = False,
    busy_timeout: int = 5000,
) -> AsyncEngine:
    """Create a configured SQLAlchemy AsyncEngine for SQLite.

    PRAGMAs — applied by ``_set_sqlite_pragmas`` on **every new DBAPI
    connection** via ``event.listen``:
    * ``foreign_keys = ON`` (per-connection; default is OFF in SQLite)
    * ``busy_timeout = {busy_timeout}`` (per-connection; default 5000ms)

    Production uses the default 5-second busy wait.  Tests may pass a
    shorter ``busy_timeout`` (e.g. 100ms) to avoid long hangs during
    real SQLite lock integration tests.

    ``journal_mode = WAL`` is database-level and persistent; it is applied
    once by the separate ``configure_engine()`` helper.
    """
    db_url = build_sqlite_url(settings)
    engine = create_async_engine(
        db_url,
        echo=echo,
        connect_args={
            "check_same_thread": False,  # required for asyncio usage
        },
    )

    # Attach per-connection PRAGMA handler to the underlying sync pool.
    # SQLAlchemy's async engine wraps a sync engine internally; we listen
    # on the sync engine's pool for the PoolEvents.connect event.
    def _set_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute(f"PRAGMA busy_timeout = {busy_timeout};")
        cursor.close()

    event.listen(engine.sync_engine, "connect", _set_pragmas)

    return engine


async def configure_engine(engine: AsyncEngine) -> None:
    """Apply database-level runtime settings to the engine.

    Call once after the engine is created, before first use.

    ``journal_mode = WAL`` is a **database-level** setting in SQLite.
    Once set, it persists across connection close/open and survives
    engine restarts.  It is applied here once during startup rather
    than on every connection.

    Per-connection settings (``foreign_keys``, ``busy_timeout``) are
    handled by ``_set_sqlite_pragmas`` attached to the engine's pool
    event in ``create_engine()``.
    """
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode = WAL;")
        await conn.commit()


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a new async_sessionmaker bound to *engine*."""
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def dispose_engine(engine: Optional[AsyncEngine]) -> None:
    """Dispose the engine, releasing all connections.

    Safe to call with *engine* = ``None``.
    """
    if engine is not None:
        await engine.dispose()