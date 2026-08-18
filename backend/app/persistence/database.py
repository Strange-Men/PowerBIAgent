"""Database engine lifecycle and session factory.

Re-exports from ``backend/app/persistence/__init__.py`` for readability.

Users should import from ``backend.app.persistence.database``:
::

    from backend.app.persistence.database import (
        build_sqlite_url,
        configure_engine,
        create_engine,
        create_session_factory,
        dispose_engine,
    )
"""

from backend.app.persistence import (
    build_sqlite_url,
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)

__all__ = [
    "build_sqlite_url",
    "configure_engine",
    "create_engine",
    "create_session_factory",
    "dispose_engine",
]