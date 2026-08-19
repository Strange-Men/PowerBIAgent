"""Shared helpers for SQLite-backed repositories — M4.1.3.

``ensure_conversation``
    Transaction-safe deterministic conversation root upsert.
    Uses SQLite native ``INSERT OR IGNORE`` so that a concurrent
    transaction inserting the same composite PK silently succeeds
    without entering a failed-transaction state.

``_resolve_locked_commit_failure``
    M4.1.3: This helper is called ONLY after the original transaction
    has fully exited (rolled back).  It uses a completely fresh
    session + transaction to re-read the latest committed version so
    the caller can decide between memory-version-conflict and
    infrastructure-failure.  Never called inside a failed transaction.

``PersistenceRepositoryError``
    Base exception for non-concurrency persistence failures
    (disk I/O, corruption, unexpected database errors).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.persistence.models import ConversationModel

if TYPE_CHECKING:
    from backend.app.memory.models import RuntimeDataMode

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
    from sqlalchemy import text as sa_text
    from sqlalchemy.exc import OperationalError

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


# ---------------------------------------------------------------------------
# Locked-commit failure resolution  (M4.1.2)
# ---------------------------------------------------------------------------


async def _resolve_locked_commit_failure(
    session_factory: async_sessionmaker[AsyncSession],
    conversation_id: str,
    runtime_mode: "RuntimeDataMode",
    target_version: int,
    *,
    _latest_committed_version_fn=None,
) -> None:
    """Resolve a SQLite locked/busy OperationalError from commit().

    **M4.1.3: Guaranteed to run AFTER the original failed transaction
    has fully exited (rolled back).**  Never called inside a poisoned
    transaction.

    Opens a *fresh* session and transaction to re-read the latest
    committed version for the given (conversation_id, runtime_mode).
    Raises the authoritative domain exception:

    * ``MemoryVersionConflictError`` — if the latest committed version
      is *at least* ``target_version`` (another writer won the race).
    * ``PersistenceRepositoryError`` — if the latest version has still
      not advanced past ``target_version`` (true infrastructure failure
      — the lock was transient but no concurrent write occurred).

    The helper is a pure reader: it never mutates business state.

    Args:
        session_factory: Factory to create the fresh session.
        conversation_id: Conversation whose version chain to inspect.
        runtime_mode: Mode scoping the version chain.
        target_version: The ``memory_version`` the failed commit
            attempted to write.
        _latest_committed_version_fn: Override for testing only.

    Raises:
        MemoryVersionConflictError: latest_version >= target_version.
        PersistenceRepositoryError: version not advanced or DB error
            in the fresh session itself.
    """
    from backend.app.memory.repository import MemoryVersionConflictError
    from backend.app.persistence.models import WorkMemoryModel
    from backend.app.memory.models import MemoryStatus

    try:
        async with session_factory() as fresh_session:
            if _latest_committed_version_fn:
                latest_version = await _latest_committed_version_fn(
                    fresh_session, conversation_id, runtime_mode
                )
            else:
                stmt = (
                    select(WorkMemoryModel.memory_version)
                    .where(
                        and_(
                            WorkMemoryModel.conversation_id == conversation_id,
                            WorkMemoryModel.runtime_mode == runtime_mode.value,
                            WorkMemoryModel.state_status
                            == MemoryStatus.COMMITTED.value,
                        )
                    )
                    .order_by(WorkMemoryModel.memory_version.desc())
                    .limit(1)
                )
                result = await fresh_session.execute(stmt)
                latest_version = result.scalar_one_or_none() or 0
    except Exception as exc:
        raise PersistenceRepositoryError(
            f"Failed to re-read latest version after locked commit: {exc}"
        ) from exc

    if latest_version >= target_version:
        raise MemoryVersionConflictError(
            f"Concurrent commit conflict (resolved after lock): "
            f"conversation_id={conversation_id}, "
            f"runtime_mode={runtime_mode.value}, "
            f"target_version={target_version}, "
            f"latest_version={latest_version}"
        )

    raise PersistenceRepositoryError(
        f"Database lock conflict — version not advanced: "
        f"latest={latest_version}, target={target_version}"
    )