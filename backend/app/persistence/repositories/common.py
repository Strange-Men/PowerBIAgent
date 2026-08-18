"""Shared helpers for SQLite-backed repositories — M4.1.1.

``ensure_conversation``
    Transaction-safe deterministic conversation root upsert.
    Uses SQLite native ``INSERT OR IGNORE`` so that a concurrent
    transaction inserting the same composite PK silently succeeds
    without entering a failed-transaction state.

``PersistenceRepositoryError``
    Base exception for non-concurrency persistence failures
    (disk I/O, corruption, unexpected database errors).
"""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models import ConversationModel

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class PersistenceRepositoryError(Exception):
    """Non-concurrency persistence error (disk I/O, corruption, etc.).

    Raised when a database operation fails for reasons *other* than
    a version conflict or a transient SQLite busy/locked condition.
    """

    pass


# ---------------------------------------------------------------------------
# Conversation root upsert
# ---------------------------------------------------------------------------

# SQLite "INSERT OR IGNORE" is the authoritative deterministic upsert.
# It atomically avoids the race inherent in SELECT→INSERT, and unlike
# catching IntegrityError after flush(), it never poisons the current
# transaction.  The composite PK (runtime_mode, conversation_id) is
# the conflict target.
_INSERT_OR_IGNORE_CONV = """
INSERT OR IGNORE INTO conversations (conversation_id, runtime_mode)
VALUES (:conversation_id, :runtime_mode)
"""


async def ensure_conversation(
    conversation_id: str,
    runtime_mode_value: str,
    session: AsyncSession,
) -> None:
    """Deterministic conversation root upsert.

    Safe under concurrent writers:
    *   ``INSERT OR IGNORE`` is atomic — if another transaction
        already inserted the same PK, the insert is a no-op, not
        an error.
    *   The transaction is never poisoned.
    *   A subsequent ``SELECT`` is still available if the caller
        needs to inspect the row afterward.

    Raises:
        PersistenceRepositoryError: unexpected DB error (not a
            duplicate-key condition).
    """
    from sqlalchemy.exc import OperationalError
    from sqlalchemy import text as sa_text

    try:
        await session.execute(
            sa_text(_INSERT_OR_IGNORE_CONV),
            {
                "conversation_id": conversation_id,
                "runtime_mode": runtime_mode_value,
            },
        )
    except OperationalError as exc:
        raise PersistenceRepositoryError(
            f"Database error while ensuring conversation "
            f"({runtime_mode_value}, {conversation_id}): {exc}"
        ) from exc