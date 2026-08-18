"""SQLiteSnapshotRepository — persistent SnapshotRepository backed by SQLite + SQLAlchemy Async.

Design notes
============
*   **Persistent snapshot storage**: ``save``, ``get``, ``exists`` are backed by
    the ``result_snapshots`` table with composite key ``(runtime_mode, request_id)``.
*   **In-flight coordination** (Owner / Waiter) is delegated to the existing
    process-local ``IdempotencyTracker`` — M4.1 does not implement distributed
    locking.
*   On service restart, completed snapshots survive in SQLite and can be
    replayed.  In-flight requests do not survive a crash (future M4.4).
*   Fingerprint conflict detection is enforced by the UNIQUE constraint on
    ``(runtime_mode, request_id)`` combined with in-memory in-flight check.
*   Corrupt payloads raise ``ValidationError`` (fail closed).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.memory.result_snapshot import (
    IdempotencyClaimStatus,
    IdempotencyTracker,
    SnapshotRepository,
    TurnResultSnapshot,
)
from backend.app.persistence.models import ConversationModel, ResultSnapshotModel
from backend.app.persistence.serialization import domain_to_json, json_to_domain
from backend.app.persistence.repositories.common import (
    PersistenceRepositoryError,
    ensure_conversation,
)


# ---------------------------------------------------------------------------
# SQLiteSnapshotRepository
# ---------------------------------------------------------------------------


class SQLiteSnapshotRepository(SnapshotRepository):
    """SnapshotRepository backed by SQLite for persistent storage, combined
    with a process-local IdempotencyTracker for in-flight Owner/Waiter
    coordination.

    Persistent state (completed snapshots) survives restarts.
    In-flight state is process-local and lost on restart.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self._idempotency = IdempotencyTracker()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _key(self, request_id: str, runtime_mode: str) -> tuple:
        return (runtime_mode, request_id)

    async def _ensure_conversation(
        self,
        conversation_id: str,
        runtime_mode_value: str,
        session: AsyncSession,
    ) -> None:
        """Transaction-safe conversation root creation.

        Delegates to the shared ``ensure_conversation`` helper which
        uses ``INSERT OR IGNORE`` — safe under concurrent writers and
        never poisons the current transaction.
        """
        await ensure_conversation(conversation_id, runtime_mode_value, session)

    # ------------------------------------------------------------------
    # Persistent storage
    # ------------------------------------------------------------------

    async def save(
        self,
        snapshot: TurnResultSnapshot,
        runtime_mode: object,
    ) -> None:
        """Persist a snapshot to SQLite.

        Overwrites an existing row with the same (runtime_mode, request_id).
        """
        mode_value = runtime_mode.value if hasattr(runtime_mode, "value") else str(runtime_mode)

        async with self._session_factory() as session:
            async with session.begin():
                await self._ensure_conversation(
                    snapshot.conversation_id, mode_value, session
                )

                # Check for existing row
                stmt = select(ResultSnapshotModel).where(
                    and_(
                        ResultSnapshotModel.request_id == snapshot.request_id,
                        ResultSnapshotModel.runtime_mode == mode_value,
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                payload = domain_to_json(snapshot)

                if existing:
                    # Update
                    existing.payload_json = payload
                    existing.request_fingerprint_hash = snapshot.request_fingerprint_hash
                    existing.terminal_state = snapshot.terminal_state
                    existing.response_type = snapshot.response_type
                    existing.conversation_id = snapshot.conversation_id
                else:
                    model = ResultSnapshotModel(
                        request_id=snapshot.request_id,
                        runtime_mode=mode_value,
                        conversation_id=snapshot.conversation_id,
                        request_fingerprint_hash=snapshot.request_fingerprint_hash,
                        terminal_state=snapshot.terminal_state,
                        response_type=snapshot.response_type,
                        payload_json=payload,
                    )
                    session.add(model)

                await session.flush()

    async def get(
        self,
        request_id: str,
        runtime_mode: object,
    ) -> Optional[TurnResultSnapshot]:
        """Retrieve a snapshot by (runtime_mode, request_id).

        Returns None if not found.
        Raises ValidationError if the stored payload is corrupt (fail closed).
        """
        mode_value = runtime_mode.value if hasattr(runtime_mode, "value") else str(runtime_mode)

        async with self._session_factory() as session:
            stmt = select(ResultSnapshotModel).where(
                and_(
                    ResultSnapshotModel.request_id == request_id,
                    ResultSnapshotModel.runtime_mode == mode_value,
                )
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return json_to_domain(TurnResultSnapshot, row.payload_json)

    async def exists(
        self,
        request_id: str,
        runtime_mode: object,
    ) -> bool:
        """Check whether a snapshot exists for (runtime_mode, request_id)."""
        mode_value = runtime_mode.value if hasattr(runtime_mode, "value") else str(runtime_mode)

        async with self._session_factory() as session:
            stmt = select(ResultSnapshotModel).where(
                and_(
                    ResultSnapshotModel.request_id == request_id,
                    ResultSnapshotModel.runtime_mode == mode_value,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # In-flight coordination (delegated to process-local IdempotencyTracker)
    # ------------------------------------------------------------------

    async def claim(
        self,
        request_id: str,
        runtime_mode: object,
        fingerprint_hash: str,
    ) -> tuple[IdempotencyClaimStatus, Optional[asyncio.Future]]:
        return await self._idempotency.claim(
            request_id, runtime_mode, fingerprint_hash
        )

    async def complete(
        self,
        request_id: str,
        runtime_mode: object,
    ) -> None:
        await self._idempotency.complete(request_id, runtime_mode)

    async def abort(
        self,
        request_id: str,
        runtime_mode: object,
    ) -> None:
        await self._idempotency.abort(request_id, runtime_mode)

    # ------------------------------------------------------------------
    # Test introspection
    # ------------------------------------------------------------------

    def _count(self) -> int:
        """Return total snapshot rows (for test introspection)."""
        import asyncio

        async def _inner() -> int:
            async with self._session_factory() as session:
                from sqlalchemy import func as sa_func, select as sa_select

                stmt = sa_select(sa_func.count(ResultSnapshotModel.id))
                result = await session.execute(stmt)
                return result.scalar() or 0

        return asyncio.run(_inner())