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


def create_engine(
    settings: Settings,
    *,
    echo: bool = False,
) -> AsyncEngine:
    """Create a configured SQLAlchemy AsyncEngine for SQLite.

    PRAGMAs applied:
    * ``foreign_keys = ON``
    * ``journal_mode = WAL``
    * ``busy_timeout = 5000`` (5 seconds — bounded, not infinite)
    """
    db_url = build_sqlite_url(settings)
    engine = create_async_engine(
        db_url,
        echo=echo,
        connect_args={
            "check_same_thread": False,  # required for asyncio usage
        },
    )
    return engine


async def configure_engine(engine: AsyncEngine) -> None:
    """Apply runtime PRAGMA settings to the engine.

    Call once after the engine is created, before first use.
    """
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.exec_driver_sql("PRAGMA journal_mode = WAL;")
        await conn.exec_driver_sql("PRAGMA busy_timeout = 5000;")
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