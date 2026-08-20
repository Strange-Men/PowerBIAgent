"""SQLiteMemoryRepository — persistent MemoryRepository backed by SQLite + SQLAlchemy Async.

Permanent business semantics
=============================
*   PENDING → COMMITTED or FAILED
*   ``base_memory_version`` tracks the version observed at the start of a turn.
*   ``memory_version = base + 1`` — assigned atomically during commit.
*   ``MemoryVersionConflictError`` raised when the current committed version
    does not match the pending memory's ``base_memory_version``.
*   ``PendingClarificationContext`` is separate from the committed version chain.
*   Mock / Real namespaces are fully isolated via composite keys.
*   Conversation roots are created deterministically (get-or-create).
"""

from __future__ import annotations

import copy
import json
from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    MemoryCommitDeniedError,
    MemoryDuplicateError,
    MemoryRepository,
    MemoryVersionConflictError,
)
from backend.app.persistence.models import (
    ConversationModel,
    PendingClarificationModel,
    WorkMemoryModel,
)
from backend.app.persistence.serialization import domain_to_json, json_to_domain
from backend.app.persistence.repositories.common import (
    PersistenceRepositoryError,
    ensure_conversation,
)

# ---------------------------------------------------------------------------
# Model ↔ Domain conversion helpers
# ---------------------------------------------------------------------------


def _work_memory_to_model(
    memory: StructuredWorkMemory,
) -> dict:
    """Convert a StructuredWorkMemory to a dict for WorkMemoryModel column values."""
    return {
        "request_id": memory.request_id,
        "conversation_id": memory.conversation_id,
        "runtime_mode": memory.runtime_mode.value,
        "state_status": memory.state_status.value,
        "base_memory_version": memory.base_memory_version,
        "memory_version": memory.memory_version,
        "semantic_model_key": memory.semantic_model_key,
        "report_template_key": memory.report_template_key,
        "current_intent": memory.current_intent,
        "analysis_goal": memory.analysis_goal,
        "payload_json": domain_to_json(memory),
        "failure_reason": memory.failure_reason,
        "failure_stage": memory.failure_stage,
    }


def _model_to_work_memory(row: WorkMemoryModel) -> StructuredWorkMemory:
    """Reconstruct a StructuredWorkMemory from a WorkMemoryModel row.

    ``payload_json`` is the complete domain reconstruction authority.  The
    dedicated columns are query/index/support fields and must never be used to
    rebuild partial executable semantic state.

    Raises PersistenceRepositoryError when the payload is missing, incomplete,
    or conflicts with the row's integrity fields. JSON/Pydantic validation
    failures propagate — all fail closed.
    """
    payload_json = row.payload_json
    if payload_json is None or not payload_json.strip():
        raise PersistenceRepositoryError("work_memory_payload_missing")

    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise PersistenceRepositoryError("work_memory_payload_invalid")
    missing_fields = sorted(
        set(StructuredWorkMemory.model_fields).difference(payload)
    )
    if missing_fields:
        raise PersistenceRepositoryError(
            "work_memory_payload_incomplete:" + ",".join(missing_fields)
        )

    memory = StructuredWorkMemory.model_validate(payload)
    integrity_fields = (
        ("request_id", row.request_id, memory.request_id),
        ("conversation_id", row.conversation_id, memory.conversation_id),
        ("runtime_mode", row.runtime_mode, memory.runtime_mode.value),
        ("state_status", row.state_status, memory.state_status.value),
        ("base_memory_version", row.base_memory_version, memory.base_memory_version),
        ("memory_version", row.memory_version, memory.memory_version),
        ("semantic_model_key", row.semantic_model_key, memory.semantic_model_key),
        ("report_template_key", row.report_template_key, memory.report_template_key),
        ("current_intent", row.current_intent, memory.current_intent),
        ("analysis_goal", row.analysis_goal, memory.analysis_goal),
        ("failure_reason", row.failure_reason, memory.failure_reason),
        ("failure_stage", row.failure_stage, memory.failure_stage),
    )
    for field_name, row_value, payload_value in integrity_fields:
        if row_value != payload_value:
            raise PersistenceRepositoryError(
                f"work_memory_row_payload_mismatch:{field_name}"
            )
    return memory


def _clarification_to_model(
    context: PendingClarificationContext,
) -> dict:
    """Convert a PendingClarificationContext to column values."""
    return {
        "conversation_id": context.conversation_id,
        "runtime_mode": context.runtime_mode.value,
        "chain_id": context.chain_id,
        "semantic_model_key": context.semantic_model_key,
        "schema_fingerprint": context.schema_fingerprint,
        "payload_json": domain_to_json(context),
    }


def _model_to_clarification(
    row: PendingClarificationModel,
) -> PendingClarificationContext:
    """Reconstruct PendingClarificationContext from a row."""
    return json_to_domain(PendingClarificationContext, row.payload_json)


# ---------------------------------------------------------------------------
# Error-semantics helpers (M4.1.1)
# ---------------------------------------------------------------------------


def _is_version_index_conflict(exc: IntegrityError) -> bool:
    """Detect whether an IntegrityError originates from the
    committed-version partial unique index.

    The index ``ix_work_memories_committed_version`` enforces:
        UNIQUE (runtime_mode, conversation_id, memory_version)
        WHERE state_status = 'committed'

    SQLite reports::
        UNIQUE constraint failed: work_memories.runtime_mode,
        work_memories.conversation_id, work_memories.memory_version

    We check for the presence of all three column names together
    in the error message.  A PK violation would list different
    columns (conversation_id, runtime_mode).
    """
    msg = str(exc).upper()
    # The three columns of the partial unique index
    c1 = "RUNTIME_MODE"
    c2 = "CONVERSATION_ID"
    c3 = "MEMORY_VERSION"
    return c1 in msg and c2 in msg and c3 in msg


def _is_sqlite_locked(exc: OperationalError) -> bool:
    """Check if an OperationalError is a SQLite busy/locked condition."""
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in ("sqlite_busy", "sqlite_locked", "database is locked", "database table is locked")
    )


# ---------------------------------------------------------------------------
# SQLiteMemoryRepository
# ---------------------------------------------------------------------------


class SQLiteMemoryRepository(MemoryRepository):
    """MemoryRepository backed by SQLite.

    Uses SQLAlchemy Async sessions. All public methods are async and safe
    for concurrent use — commit atomicity is guaranteed by the SQLite
    transaction and the UNIQUE + version-check constraints.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Conversation root (deterministic get-or-create)
    # ------------------------------------------------------------------

    async def _ensure_conversation(
        self,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
        session: AsyncSession,
    ) -> None:
        """Transaction-safe conversation root creation.

        Delegates to the shared ``ensure_conversation`` helper which
        uses ``INSERT OR IGNORE`` — safe under concurrent writers and
        never poisons the current transaction.
        """
        await ensure_conversation(conversation_id, runtime_mode.value, session)

    # ------------------------------------------------------------------
    # MemoryRepository interface
    # ------------------------------------------------------------------

    async def create_pending(
        self,
        memory: StructuredWorkMemory,
        runtime_mode: RuntimeDataMode,
    ) -> StructuredWorkMemory:
        async with self._session_factory() as session:
            async with session.begin():
                # Check duplicate
                stmt = select(WorkMemoryModel).where(
                    and_(
                        WorkMemoryModel.request_id == memory.request_id,
                        WorkMemoryModel.runtime_mode == runtime_mode.value,
                    )
                )
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    raise MemoryDuplicateError(
                        f"request_id '{memory.request_id}' 在 "
                        f"'{runtime_mode.value}' 模式已存在，不重复创建"
                    )

                await self._ensure_conversation(
                    memory.conversation_id, runtime_mode, session
                )

                stored = copy.deepcopy(memory)
                stored.state_status = MemoryStatus.PENDING
                stored.runtime_mode = runtime_mode

                cols = _work_memory_to_model(stored)
                model = WorkMemoryModel(**cols)
                session.add(model)
                await session.flush()

            return stored

    async def get_by_request_id(
        self,
        request_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> Optional[StructuredWorkMemory]:
        async with self._session_factory() as session:
            stmt = select(WorkMemoryModel).where(
                and_(
                    WorkMemoryModel.request_id == request_id,
                    WorkMemoryModel.runtime_mode == runtime_mode.value,
                )
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _model_to_work_memory(row)

    async def get_latest_committed(
        self,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> Optional[StructuredWorkMemory]:
        async with self._session_factory() as session:
            conditions = [
                WorkMemoryModel.conversation_id == conversation_id,
                WorkMemoryModel.runtime_mode == runtime_mode.value,
                WorkMemoryModel.state_status == MemoryStatus.COMMITTED.value,
            ]

            stmt = (
                select(WorkMemoryModel)
                .where(and_(*conditions))
                .order_by(WorkMemoryModel.memory_version.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _model_to_work_memory(row)

    async def commit(
        self,
        memory: StructuredWorkMemory,
        evidence: MemoryCommitEvidence,
    ) -> StructuredWorkMemory:
        """Atomic commit with version check and DB-level invariant.

        M4.1.3: Locked/busy OperationalError is captured inside the
        transaction but resolved AFTER the transaction exits (rolls
        back).  This guarantees the original failed transaction fully
        terminates before a fresh-session reader touches the DB.

        Success path (all within a single database transaction):
        1. Verify memory is PENDING
        2. Verify business evidence satisfied
        3. Query latest committed version for this (conversation, mode)
        4. Verify base_memory_version matches
        5. Set evidence.version_matches = True
        6. memory_version = base + 1
        7. state_status = COMMITTED
        8. Persist commit_evidence
        9. transaction commit

        The DB-level partial unique index
        ``ix_work_memories_committed_version`` enforces that only one
        row per (runtime_mode, conversation_id, memory_version) can be
        COMMITTED.  If a concurrent transaction won the race, the
        IntegrityError from the index is converted to
        ``MemoryVersionConflictError``.

        Raises:
            MemoryCommitDeniedError: pending/evidence check fails
            MemoryVersionConflictError: stale base version or
                concurrent commit conflict
        """
        runtime_mode = memory.runtime_mode

        # M4.1.3: locked-failure state captured inside the transaction
        # but resolved OUTSIDE it, after rollback completes.
        _locked_failure_ctx: Optional[dict] = None

        async with self._session_factory() as session:
            async with session.begin():
                # 1. Fetch the existing pending row
                stmt = select(WorkMemoryModel).where(
                    and_(
                        WorkMemoryModel.request_id == memory.request_id,
                        WorkMemoryModel.runtime_mode == runtime_mode.value,
                    )
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()

                if row is None:
                    raise MemoryCommitDeniedError(
                        f"request_id '{memory.request_id}' 在 "
                        f"'{runtime_mode.value}' 模式不存在"
                    )

                # 2. State check
                if row.state_status != MemoryStatus.PENDING.value:
                    raise MemoryCommitDeniedError(
                        f"仅有 pending 状态可以提交，当前状态: {row.state_status}"
                    )

                # 3. Business evidence check
                if evidence.failure_reason is not None and evidence.failure_reason != "":
                    raise MemoryCommitDeniedError(
                        f"存在失败原因，不可提交: {evidence.failure_reason}"
                    )

                if evidence.intent_valid is False:
                    raise MemoryCommitDeniedError("意图无效，不可提交")

                if evidence.request_allowed is False:
                    raise MemoryCommitDeniedError("请求未被允许，不可提交")

                if not evidence.business_satisfied:
                    missing = []
                    if not evidence.query_plan_valid:
                        missing.append("query_plan_valid")
                    if not evidence.dax_valid:
                        missing.append("dax_valid")
                    if not evidence.tool_execution_succeeded:
                        missing.append("tool_execution_succeeded")
                    if not evidence.query_result_valid:
                        missing.append("query_result_valid")
                    if not evidence.response_valid:
                        missing.append("response_valid")
                    raise MemoryCommitDeniedError(
                        f"业务证据不完整: {', '.join(missing)}"
                    )

                # 4. Mode consistency
                if runtime_mode.value != row.runtime_mode:
                    raise MemoryCommitDeniedError(
                        f"运行时模式不一致: {runtime_mode.value} vs {row.runtime_mode}"
                    )

                # 5. Version conflict check — read latest committed for this conversation+mode
                latest_version = await self._get_latest_committed_version(
                    session, memory.conversation_id, runtime_mode
                )

                base_version = memory.base_memory_version
                if base_version != latest_version:
                    raise MemoryVersionConflictError(
                        f"版本冲突: 期望 base 版本 {base_version}, "
                        f"当前会话最新 committed 版本 {latest_version}"
                    )

                # 6. Reconstruct the full domain model from the stored payload
                #    so we can merge changes from *memory* onto it.
                existing_domain = _model_to_work_memory(row)

                # Merge analysis fields from the caller's memory
                existing_domain.current_intent = memory.current_intent
                existing_domain.analysis_goal = memory.analysis_goal
                existing_domain.semantic_model_key = memory.semantic_model_key
                existing_domain.report_template_key = memory.report_template_key
                existing_domain.measures = copy.deepcopy(memory.measures)
                existing_domain.dimensions = copy.deepcopy(memory.dimensions)
                existing_domain.filters = copy.deepcopy(memory.filters)
                existing_domain.time_range = memory.time_range
                existing_domain.sort = memory.sort
                existing_domain.top_n = memory.top_n
                existing_domain.comparison_mode = memory.comparison_mode
                existing_domain.last_query_plan = copy.deepcopy(memory.last_query_plan)
                existing_domain.last_dax = memory.last_dax
                existing_domain.last_query_result_id = memory.last_query_result_id
                existing_domain.last_result_summary = memory.last_result_summary
                existing_domain.last_report_id = memory.last_report_id
                existing_domain.runtime_mode = memory.runtime_mode
                existing_domain.is_mock = memory.is_mock
                existing_domain.llm_provider = memory.llm_provider
                existing_domain.powerbi_provider = memory.powerbi_provider
                existing_domain.updated_at = memory.updated_at

                # 7. Atomic commit — stamp and persist
                evidence.version_matches = True
                existing_domain._mark_committed(evidence)

                # 8. Update the row — memory_version and state_status are set
                #    here.  The DB-level partial unique index
                #    ``ix_work_memories_committed_version`` guarantees that
                #    only one row per (runtime_mode, conversation_id,
                #    memory_version) can be COMMITTED.
                new_version = existing_domain.memory_version
                new_payload = domain_to_json(existing_domain)

                try:
                    update_stmt = (
                        update(WorkMemoryModel)
                        .where(WorkMemoryModel.id == row.id)
                        .values(
                            state_status=MemoryStatus.COMMITTED.value,
                            memory_version=new_version,
                            base_memory_version=existing_domain.base_memory_version,
                            payload_json=new_payload,
                            current_intent=existing_domain.current_intent,
                            analysis_goal=existing_domain.analysis_goal,
                            semantic_model_key=existing_domain.semantic_model_key,
                            report_template_key=existing_domain.report_template_key,
                            failure_reason=existing_domain.failure_reason,
                            failure_stage=existing_domain.failure_stage,
                            updated_at=func.now(),
                        )
                    )
                    await session.execute(update_stmt)
                except IntegrityError as exc:
                    # Only convert version-unique-constraint violations to
                    # MemoryVersionConflictError.  Other IntegrityError
                    # types (PK, FK, NOT NULL) are re-raised.
                    if _is_version_index_conflict(exc):
                        raise MemoryVersionConflictError(
                            f"并发提交冲突: (runtime_mode={runtime_mode.value}, "
                            f"conversation_id={memory.conversation_id}, "
                            f"memory_version={new_version}) 版本冲突, "
                            f"当前 base 版本 {memory.base_memory_version}"
                        ) from exc
                    raise
                except OperationalError as exc:
                    # M4.1.3: ONLY capture failure context inside the
                    # transaction — do NOT call fresh-session resolver
                    # here.  Let the transaction roll back first.
                    if not _is_sqlite_locked(exc):
                        raise PersistenceRepositoryError(
                            f"数据库错误 (非锁): {exc}"
                        ) from exc
                    _locked_failure_ctx = {
                        "conversation_id": memory.conversation_id,
                        "runtime_mode": runtime_mode,
                        "target_version": new_version,
                        "original_exc": exc,
                    }

            # ------------------------------------------------------------------
            # M4.1.3: Transaction context exited (rolled back).
            #         NOW resolve the locked failure with a fresh session.
            # ------------------------------------------------------------------
            if _locked_failure_ctx is not None:
                from backend.app.persistence.repositories.common import (
                    _resolve_locked_commit_failure,
                )

                await _resolve_locked_commit_failure(
                    self._session_factory,
                    _locked_failure_ctx["conversation_id"],
                    _locked_failure_ctx["runtime_mode"],
                    target_version=_locked_failure_ctx["target_version"],
                )
                # _resolve_locked_commit_failure always raises one of
                # MemoryVersionConflictError or PersistenceRepositoryError.
                # This line is unreachable — keep as safety net.
                raise PersistenceRepositoryError(
                    f"Unexpected: locked commit helper returned without raising "
                    f"for (conversation={_locked_failure_ctx['conversation_id']}, "
                    f"mode={_locked_failure_ctx['runtime_mode'].value}, "
                    f"target={_locked_failure_ctx['target_version']})"
                ) from _locked_failure_ctx["original_exc"]

            # After commit, return the domain model
            return existing_domain

    async def mark_failed(
        self,
        request_id: str,
        runtime_mode: RuntimeDataMode,
        reason: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Optional[StructuredWorkMemory]:
        async with self._session_factory() as session:
            async with session.begin():
                stmt = select(WorkMemoryModel).where(
                    and_(
                        WorkMemoryModel.request_id == request_id,
                        WorkMemoryModel.runtime_mode == runtime_mode.value,
                    )
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None

                # Reconstruct domain, mark failed, persist
                domain = _model_to_work_memory(row)

                domain._mark_failed(reason=reason, stage=stage)
                new_payload = domain_to_json(domain)

                update_stmt = (
                    update(WorkMemoryModel)
                    .where(WorkMemoryModel.id == row.id)
                    .values(
                        state_status=MemoryStatus.FAILED.value,
                        failure_reason=reason,
                        failure_stage=stage,
                        payload_json=new_payload,
                        updated_at=func.now(),
                    )
                )
                await session.execute(update_stmt)

            return domain

    async def list_by_conversation(
        self,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[StructuredWorkMemory]:
        async with self._session_factory() as session:
            conditions = [
                WorkMemoryModel.conversation_id == conversation_id,
                WorkMemoryModel.runtime_mode == runtime_mode.value,
            ]
            if status is not None:
                conditions.append(WorkMemoryModel.state_status == status)

            stmt = (
                select(WorkMemoryModel)
                .where(and_(*conditions))
                .order_by(WorkMemoryModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [_model_to_work_memory(r) for r in rows]

    async def request_exists(
        self,
        request_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> bool:
        async with self._session_factory() as session:
            stmt = select(WorkMemoryModel).where(
                and_(
                    WorkMemoryModel.request_id == request_id,
                    WorkMemoryModel.runtime_mode == runtime_mode.value,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Pending Clarification
    # ------------------------------------------------------------------

    async def save_pending_clarification(
        self,
        context: PendingClarificationContext,
        runtime_mode: RuntimeDataMode,
    ) -> PendingClarificationContext:
        """Upsert: create or replace the single clarification for this
        (runtime_mode, conversation_id)."""
        async with self._session_factory() as session:
            async with session.begin():
                await self._ensure_conversation(
                    context.conversation_id, runtime_mode, session
                )

                stored = context.model_copy(
                    deep=True, update={"runtime_mode": runtime_mode}
                )

                # Check existing
                stmt = select(PendingClarificationModel).where(
                    and_(
                        PendingClarificationModel.conversation_id
                        == context.conversation_id,
                        PendingClarificationModel.runtime_mode
                        == runtime_mode.value,
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                cols = _clarification_to_model(stored)

                if existing:
                    # Update
                    update_stmt = (
                        update(PendingClarificationModel)
                        .where(PendingClarificationModel.id == existing.id)
                        .values(**cols, updated_at=func.now())
                    )
                    await session.execute(update_stmt)
                else:
                    # Insert
                    model = PendingClarificationModel(**cols)
                    session.add(model)
                    await session.flush()

            return stored

    async def get_pending_clarification(
        self,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> Optional[PendingClarificationContext]:
        async with self._session_factory() as session:
            stmt = select(PendingClarificationModel).where(
                and_(
                    PendingClarificationModel.conversation_id == conversation_id,
                    PendingClarificationModel.runtime_mode == runtime_mode.value,
                )
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _model_to_clarification(row)

    async def clear_pending_clarification(
        self,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> Optional[PendingClarificationContext]:
        async with self._session_factory() as session:
            async with session.begin():
                stmt = select(PendingClarificationModel).where(
                    and_(
                        PendingClarificationModel.conversation_id == conversation_id,
                        PendingClarificationModel.runtime_mode == runtime_mode.value,
                    )
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None

                context = _model_to_clarification(row)
                await session.delete(row)
                await session.flush()

            return context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_latest_committed_version(
        self,
        session: AsyncSession,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> int:
        """Get the highest committed memory_version for a conversation/mode pair."""
        stmt = (
            select(WorkMemoryModel.memory_version)
            .where(
                and_(
                    WorkMemoryModel.conversation_id == conversation_id,
                    WorkMemoryModel.runtime_mode == runtime_mode.value,
                    WorkMemoryModel.state_status == MemoryStatus.COMMITTED.value,
                )
            )
            .order_by(WorkMemoryModel.memory_version.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row is not None else 0

    def _get_session_count(self) -> int:
        """Return total rows in work_memories (for test introspection)."""
        import asyncio

        async def _count() -> int:
            async with self._session_factory() as session:
                from sqlalchemy import func as sa_func, select as sa_select

                stmt = sa_select(sa_func.count(WorkMemoryModel.id))
                result = await session.execute(stmt)
                return result.scalar() or 0

        return asyncio.run(_count())
