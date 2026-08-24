"""SQLite implementation of namespace-first conversation history/search."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import and_, case, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.conversation.models import (
    CommittedMemorySummary,
    ConversationArchiveResult,
    ConversationHistoryCorruptionError,
    ConversationHistoryItem,
    ConversationNotFoundError,
    ConversationReportItem,
    ConversationRenameResult,
    ConversationRestoreResult,
    ConversationSummary,
    SnapshotReportSummary,
)
from backend.app.conversation.title import normalize_conversation_title
from backend.app.conversation.repository import (
    ConversationHistoryRepository,
    ConversationPosition,
    HistoryPosition,
    HistoryRepositoryPage,
    ReportPosition,
    RepositoryDeleteResult,
    RepositoryPage,
)
from backend.app.memory.models import MemoryStatus, RuntimeDataMode
from backend.app.memory.result_snapshot import TurnResultSnapshot
from backend.app.persistence.models import (
    ConversationModel,
    ConversationDeleteIntentModel,
    PendingClarificationModel,
    ReportArtifactModel,
    ReportDeleteIntentModel,
    ResultSnapshotModel,
    WorkMemoryModel,
)
from backend.app.persistence.repositories.report_artifact import _model_to_artifact
from backend.app.persistence.serialization import json_to_domain


class SQLiteConversationHistoryRepository(ConversationHistoryRepository):
    """Read/query lifecycle repository scoped by the namespace at every method."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def _get_conversation(
        self,
        session: AsyncSession,
        runtime_mode: RuntimeDataMode,
        conversation_id: str,
    ) -> ConversationModel:
        result = await session.execute(
            select(ConversationModel).where(
                and_(
                    ConversationModel.runtime_mode == runtime_mode.value,
                    ConversationModel.conversation_id == conversation_id,
                )
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ConversationNotFoundError("conversation_not_found")
        return row

    async def _summaries(
        self,
        session: AsyncSession,
        runtime_mode: RuntimeDataMode,
        rows: list[ConversationModel],
    ) -> list[ConversationSummary]:
        if not rows:
            return []
        conversation_ids = [row.conversation_id for row in rows]

        snapshot_result = await session.execute(
            select(ResultSnapshotModel)
            .where(
                and_(
                    ResultSnapshotModel.runtime_mode == runtime_mode.value,
                    ResultSnapshotModel.conversation_id.in_(conversation_ids),
                )
            )
            .order_by(
                ResultSnapshotModel.conversation_id.asc(),
                ResultSnapshotModel.created_at.desc(),
                ResultSnapshotModel.id.desc(),
            )
        )
        latest_snapshots: dict[str, ResultSnapshotModel] = {}
        for snapshot in snapshot_result.scalars().all():
            latest_snapshots.setdefault(snapshot.conversation_id, snapshot)

        memory_result = await session.execute(
            select(WorkMemoryModel)
            .where(
                and_(
                    WorkMemoryModel.runtime_mode == runtime_mode.value,
                    WorkMemoryModel.conversation_id.in_(conversation_ids),
                    WorkMemoryModel.state_status == MemoryStatus.COMMITTED.value,
                )
            )
            .order_by(
                WorkMemoryModel.conversation_id.asc(),
                WorkMemoryModel.created_at.desc(),
                WorkMemoryModel.id.desc(),
            )
        )
        latest_memories: dict[str, WorkMemoryModel] = {}
        for memory in memory_result.scalars().all():
            latest_memories.setdefault(memory.conversation_id, memory)

        summaries: list[ConversationSummary] = []
        for row in rows:
            snapshot = latest_snapshots.get(row.conversation_id)
            memory = latest_memories.get(row.conversation_id)
            summaries.append(
                ConversationSummary(
                    runtime_mode=runtime_mode,
                    conversation_id=row.conversation_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    archived_at=row.archived_at,
                    title=row.title,
                    latest_request_id=(snapshot.request_id if snapshot else None),
                    latest_terminal_state=(
                        snapshot.terminal_state if snapshot else None
                    ),
                    latest_response_type=(
                        snapshot.response_type if snapshot else None
                    ),
                    latest_analysis_goal=(memory.analysis_goal if memory else None),
                )
            )
        return summaries

    @staticmethod
    def _conversation_cursor_condition(after: ConversationPosition):
        return or_(
            ConversationModel.updated_at < after.updated_at,
            and_(
                ConversationModel.updated_at == after.updated_at,
                ConversationModel.conversation_id > after.conversation_id,
            ),
        )

    async def list_recent(
        self,
        runtime_mode: RuntimeDataMode,
        *,
        limit: int,
        after: ConversationPosition | None,
    ) -> RepositoryPage[ConversationSummary, ConversationPosition]:
        conditions = [
            ConversationModel.runtime_mode == runtime_mode.value,
            ConversationModel.archived_at.is_(None),
        ]
        if after is not None:
            conditions.append(self._conversation_cursor_condition(after))
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationModel)
                .where(and_(*conditions))
                .order_by(
                    ConversationModel.updated_at.desc(),
                    ConversationModel.conversation_id.asc(),
                )
                .limit(limit + 1)
            )
            fetched = list(result.scalars().all())
            page_rows = fetched[:limit]
            summaries = await self._summaries(session, runtime_mode, page_rows)
        next_position = None
        if len(fetched) > limit and page_rows:
            last = page_rows[-1]
            next_position = ConversationPosition(
                updated_at=last.updated_at,
                conversation_id=last.conversation_id,
            )
        return RepositoryPage(items=summaries, next_position=next_position)

    async def list_archived(
        self,
        runtime_mode: RuntimeDataMode,
        *,
        limit: int,
        after: ConversationPosition | None,
    ) -> RepositoryPage[ConversationSummary, ConversationPosition]:
        conditions = [
            ConversationModel.runtime_mode == runtime_mode.value,
            ConversationModel.archived_at.is_not(None),
        ]
        if after is not None:
            conditions.append(self._conversation_cursor_condition(after))
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationModel)
                .where(and_(*conditions))
                .order_by(
                    ConversationModel.updated_at.desc(),
                    ConversationModel.conversation_id.asc(),
                )
                .limit(limit + 1)
            )
            fetched = list(result.scalars().all())
            page_rows = fetched[:limit]
            summaries = await self._summaries(session, runtime_mode, page_rows)
        next_position = None
        if len(fetched) > limit and page_rows:
            last = page_rows[-1]
            next_position = ConversationPosition(
                updated_at=last.updated_at,
                conversation_id=last.conversation_id,
            )
        return RepositoryPage(items=summaries, next_position=next_position)

    async def get_history(
        self,
        runtime_mode: RuntimeDataMode,
        conversation_id: str,
        *,
        limit: int,
        after: HistoryPosition | None,
    ) -> HistoryRepositoryPage:
        async with self._session_factory() as session:
            conversation = await self._get_conversation(
                session, runtime_mode, conversation_id
            )
            conditions = [
                ResultSnapshotModel.runtime_mode == runtime_mode.value,
                ResultSnapshotModel.conversation_id == conversation_id,
            ]
            if after is not None:
                conditions.append(
                    or_(
                        ResultSnapshotModel.created_at < after.created_at,
                        and_(
                            ResultSnapshotModel.created_at == after.created_at,
                            ResultSnapshotModel.id < after.row_id,
                        ),
                    )
                )
            result = await session.execute(
                select(ResultSnapshotModel)
                .where(and_(*conditions))
                .order_by(
                    ResultSnapshotModel.created_at.desc(),
                    ResultSnapshotModel.id.desc(),
                )
                .limit(limit + 1)
            )
            fetched = list(result.scalars().all())
            page_rows = fetched[:limit]
            request_ids = [row.request_id for row in page_rows]
            memories: dict[str, WorkMemoryModel] = {}
            owned_reports: set[tuple[str, str]] = set()
            if request_ids:
                memory_result = await session.execute(
                    select(WorkMemoryModel).where(
                        and_(
                            WorkMemoryModel.runtime_mode == runtime_mode.value,
                            WorkMemoryModel.conversation_id == conversation_id,
                            WorkMemoryModel.request_id.in_(request_ids),
                            WorkMemoryModel.state_status
                            == MemoryStatus.COMMITTED.value,
                        )
                    )
                )
                memories = {
                    row.request_id: row for row in memory_result.scalars().all()
                }
                report_result = await session.execute(
                    select(
                        ReportArtifactModel.report_id,
                        ReportArtifactModel.request_id,
                    ).where(
                        and_(
                            ReportArtifactModel.source_mode == runtime_mode.value,
                            ReportArtifactModel.conversation_id == conversation_id,
                            ReportArtifactModel.request_id.in_(request_ids),
                        )
                    )
                )
                owned_reports = {
                    (report_id, request_id)
                    for report_id, request_id in report_result.all()
                    if request_id is not None
                }

            items = [
                self._history_item(
                    row,
                    runtime_mode,
                    memories.get(row.request_id),
                    owned_reports,
                )
                for row in page_rows
            ]
        next_position = None
        if len(fetched) > limit and page_rows:
            last = page_rows[-1]
            next_position = HistoryPosition(
                created_at=last.created_at, row_id=last.id
            )
        return HistoryRepositoryPage(
            archived_at=conversation.archived_at,
            title=conversation.title,
            items=items,
            next_position=next_position,
        )

    @staticmethod
    def _history_item(
        row: ResultSnapshotModel,
        runtime_mode: RuntimeDataMode,
        memory: WorkMemoryModel | None,
        owned_reports: set[tuple[str, str]],
    ) -> ConversationHistoryItem:
        try:
            snapshot = json_to_domain(TurnResultSnapshot, row.payload_json)
        except Exception as exc:
            raise ConversationHistoryCorruptionError(
                "result_snapshot_payload_invalid"
            ) from exc
        coherent = (
            snapshot.request_id == row.request_id
            and snapshot.conversation_id == row.conversation_id
            and snapshot.terminal_state == row.terminal_state
            and snapshot.response_type == row.response_type
            and snapshot.source_mode == runtime_mode.value
        )
        if not coherent:
            raise ConversationHistoryCorruptionError(
                "result_snapshot_row_payload_mismatch"
            )

        memory_summary = None
        if memory is not None:
            memory_summary = CommittedMemorySummary(
                request_id=memory.request_id,
                memory_version=memory.memory_version,
                semantic_model_key=memory.semantic_model_key,
                report_template_key=memory.report_template_key,
                current_intent=memory.current_intent,
                analysis_goal=memory.analysis_goal,
                updated_at=memory.updated_at,
            )
        report_summary = None
        report_is_owned = bool(
            snapshot.report is not None
            and (snapshot.report.report_id, snapshot.request_id) in owned_reports
        )
        if snapshot.report is not None and report_is_owned:
            report_summary = SnapshotReportSummary(
                report_id=snapshot.report.report_id,
                template_key=snapshot.report.template_key,
                contract_version=snapshot.report.contract_version,
                view_reference=snapshot.report.view_reference,
                download_reference=snapshot.report.download_reference,
                content_type=snapshot.report.content_type,
                content_hash=snapshot.report.content_hash,
            )
        presentation = snapshot.presentation
        if presentation is not None and not report_is_owned:
            presentation = presentation.model_copy(
                update={
                    "blocks": [
                        block
                        for block in presentation.blocks
                        if block.type != "report_attachment"
                    ]
                }
            )
        return ConversationHistoryItem(
            request_id=snapshot.request_id,
            created_at=row.created_at,
            terminal_state=snapshot.terminal_state,
            response_type=snapshot.response_type,
            intent=snapshot.intent,
            user_message=(
                snapshot.user_message
                or SQLiteConversationHistoryRepository._legacy_user_message(
                    memory
                )
            ),
            presentation=presentation,
            answer=snapshot.answer,
            report=report_summary,
            clarification_question=snapshot.clarification_question,
            unsupported_reason=snapshot.unsupported_reason,
            error_type=snapshot.error_type,
            memory_commit=snapshot.memory_commit,
            final_memory_version=snapshot.final_memory_version,
            memory=memory_summary,
        )

    @staticmethod
    def _legacy_user_message(memory: WorkMemoryModel | None) -> str | None:
        """Recover only the exact legacy display prefix; never infer transcript."""
        if memory is None or not memory.analysis_goal:
            return None
        prefix = "用户提问: "
        if not memory.analysis_goal.startswith(prefix):
            return None
        value = memory.analysis_goal[len(prefix) :].strip()
        return value or None

    @staticmethod
    def _json_text(path: str):
        """Extract one declared string field without searching whole JSON/HTML."""
        return case(
            (
                func.json_valid(ResultSnapshotModel.payload_json) == 1,
                func.coalesce(
                    func.json_extract(ResultSnapshotModel.payload_json, path), ""
                ),
            ),
            else_="",
        )

    async def search(
        self,
        runtime_mode: RuntimeDataMode,
        query: str,
        *,
        limit: int,
        after: ConversationPosition | None,
    ) -> RepositoryPage[ConversationSummary, ConversationPosition]:
        needle = query.casefold()
        memory_match = exists(
            select(WorkMemoryModel.id).where(
                and_(
                    WorkMemoryModel.runtime_mode == runtime_mode.value,
                    WorkMemoryModel.conversation_id
                    == ConversationModel.conversation_id,
                    WorkMemoryModel.state_status == MemoryStatus.COMMITTED.value,
                    func.instr(
                        func.lower(func.coalesce(WorkMemoryModel.analysis_goal, "")),
                        needle,
                    )
                    > 0,
                )
            )
        ).correlate(ConversationModel)
        snapshot_text_match = or_(
            *[
                func.instr(func.lower(self._json_text(path)), needle) > 0
                for path in (
                    "$.user_message",
                    "$.answer",
                    "$.clarification_question",
                    "$.unsupported_reason",
                )
            ]
        )
        snapshot_match = exists(
            select(ResultSnapshotModel.id).where(
                and_(
                    ResultSnapshotModel.runtime_mode == runtime_mode.value,
                    ResultSnapshotModel.conversation_id
                    == ConversationModel.conversation_id,
                    snapshot_text_match,
                )
            )
        ).correlate(ConversationModel)
        conditions = [
            ConversationModel.runtime_mode == runtime_mode.value,
            ConversationModel.archived_at.is_(None),
            or_(
                func.instr(
                    func.lower(func.coalesce(ConversationModel.title, "")), needle
                )
                > 0,
                memory_match,
                snapshot_match,
            ),
        ]
        if after is not None:
            conditions.append(self._conversation_cursor_condition(after))
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationModel)
                .where(and_(*conditions))
                .order_by(
                    ConversationModel.updated_at.desc(),
                    ConversationModel.conversation_id.asc(),
                )
                .limit(limit + 1)
            )
            fetched = list(result.scalars().all())
            page_rows = fetched[:limit]
            summaries = await self._summaries(session, runtime_mode, page_rows)
        next_position = None
        if len(fetched) > limit and page_rows:
            last = page_rows[-1]
            next_position = ConversationPosition(
                updated_at=last.updated_at,
                conversation_id=last.conversation_id,
            )
        return RepositoryPage(items=summaries, next_position=next_position)

    async def list_reports(
        self,
        source_mode: RuntimeDataMode,
        conversation_id: str,
        *,
        limit: int,
        after: ReportPosition | None,
    ) -> RepositoryPage[ConversationReportItem, ReportPosition]:
        conditions = [
            ReportArtifactModel.source_mode == source_mode.value,
            ReportArtifactModel.conversation_id == conversation_id,
        ]
        if after is not None:
            conditions.append(
                or_(
                    ReportArtifactModel.created_at < after.created_at,
                    and_(
                        ReportArtifactModel.created_at == after.created_at,
                        ReportArtifactModel.report_id < after.report_id,
                    ),
                )
            )
        async with self._session_factory() as session:
            await self._get_conversation(session, source_mode, conversation_id)
            result = await session.execute(
                select(ReportArtifactModel)
                .where(and_(*conditions))
                .order_by(
                    ReportArtifactModel.created_at.desc(),
                    ReportArtifactModel.report_id.desc(),
                )
                .limit(limit + 1)
            )
            fetched = list(result.scalars().all())
            page_rows = fetched[:limit]
            items: list[ConversationReportItem] = []
            for row in page_rows:
                artifact = _model_to_artifact(row)
                items.append(
                    ConversationReportItem(
                        report_id=artifact.report_id,
                        source_mode=artifact.source_mode,
                        conversation_id=conversation_id,
                        request_id=artifact.request_id,
                        template_key=artifact.template_key,
                        semantic_model_key=artifact.semantic_model_key,
                        schema_fingerprint=artifact.schema_fingerprint,
                        contract_version=artifact.contract_version,
                        generated_at=artifact.generated_at,
                        stored_at=row.created_at,
                        content_type=artifact.content_type,
                        content_hash=artifact.content_hash,
                        view_reference=artifact.view_reference,
                        download_reference=artifact.download_reference,
                        verified_fact_set_ids=artifact.verified_fact_set_ids,
                        query_result_ids=artifact.query_result_ids,
                    )
                )
        next_position = None
        if len(fetched) > limit and page_rows:
            last = page_rows[-1]
            next_position = ReportPosition(
                created_at=last.created_at, report_id=last.report_id
            )
        return RepositoryPage(items=items, next_position=next_position)

    async def archive(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> ConversationArchiveResult:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._get_conversation(
                    session, runtime_mode, conversation_id
                )
                if row.archived_at is None:
                    archived_at = datetime.utcnow()
                    row.archived_at = archived_at
                    row.updated_at = archived_at
                    await session.flush()
                else:
                    archived_at = row.archived_at
        return ConversationArchiveResult(
            runtime_mode=runtime_mode,
            conversation_id=conversation_id,
            archived_at=archived_at,
        )

    async def restore(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> ConversationRestoreResult:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._get_conversation(
                    session, runtime_mode, conversation_id
                )
                updated_at = datetime.utcnow()
                row.archived_at = None
                row.updated_at = updated_at
                await session.flush()
        return ConversationRestoreResult(
            runtime_mode=runtime_mode,
            conversation_id=conversation_id,
            updated_at=updated_at,
        )

    async def rename(
        self,
        runtime_mode: RuntimeDataMode,
        conversation_id: str,
        title: str,
    ) -> ConversationRenameResult:
        normalized = normalize_conversation_title(title)
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._get_conversation(
                    session, runtime_mode, conversation_id
                )
                row.title = normalized
                row.updated_at = datetime.utcnow()
                await session.flush()
                updated_at = row.updated_at
        return ConversationRenameResult(
            runtime_mode=runtime_mode,
            conversation_id=conversation_id,
            title=normalized,
            updated_at=updated_at,
        )

    async def delete(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> RepositoryDeleteResult:
        async with self._session_factory() as session:
            async with session.begin():
                intent_result = await session.execute(
                    select(ConversationDeleteIntentModel).where(
                        and_(
                            ConversationDeleteIntentModel.runtime_mode
                            == runtime_mode.value,
                            ConversationDeleteIntentModel.conversation_id
                            == conversation_id,
                        )
                    )
                )
                intent = intent_result.scalar_one_or_none()
                if intent is not None:
                    return self._delete_result_from_intent(intent)

                await self._get_conversation(session, runtime_mode, conversation_id)
                report_result = await session.execute(
                    select(ReportArtifactModel.report_id).where(
                        and_(
                            ReportArtifactModel.source_mode == runtime_mode.value,
                            ReportArtifactModel.conversation_id == conversation_id,
                        )
                    )
                )
                report_ids = list(report_result.scalars().all())
                pending_report_result = await session.execute(
                    select(ReportDeleteIntentModel.report_id).where(
                        and_(
                            ReportDeleteIntentModel.source_mode == runtime_mode.value,
                            ReportDeleteIntentModel.conversation_id == conversation_id,
                        )
                    )
                )
                report_ids.extend(
                    report_id
                    for report_id in pending_report_result.scalars().all()
                    if report_id not in report_ids
                )
                deleted_counts: dict[str, int] = {}
                for name, model, mode_column in (
                    (
                        "pending_clarifications",
                        PendingClarificationModel,
                        PendingClarificationModel.runtime_mode,
                    ),
                    ("result_snapshots", ResultSnapshotModel, ResultSnapshotModel.runtime_mode),
                    ("work_memories", WorkMemoryModel, WorkMemoryModel.runtime_mode),
                ):
                    result = await session.execute(
                        delete(model).where(
                            and_(
                                mode_column == runtime_mode.value,
                                model.conversation_id == conversation_id,
                            )
                        )
                    )
                    deleted_counts[name] = max(result.rowcount or 0, 0)
                report_delete = await session.execute(
                    delete(ReportArtifactModel).where(
                        and_(
                            ReportArtifactModel.source_mode == runtime_mode.value,
                            ReportArtifactModel.conversation_id == conversation_id,
                        )
                    )
                )
                deleted_counts["report_artifacts"] = max(
                    report_delete.rowcount or 0, 0
                )
                await session.execute(
                    delete(ReportDeleteIntentModel).where(
                        and_(
                            ReportDeleteIntentModel.source_mode == runtime_mode.value,
                            ReportDeleteIntentModel.conversation_id == conversation_id,
                        )
                    )
                )
                await session.execute(
                    delete(ConversationModel).where(
                        and_(
                            ConversationModel.runtime_mode == runtime_mode.value,
                            ConversationModel.conversation_id == conversation_id,
                        )
                    )
                )
                ordered_counts = {
                    "work_memories": deleted_counts["work_memories"],
                    "result_snapshots": deleted_counts["result_snapshots"],
                    "pending_clarifications": deleted_counts[
                        "pending_clarifications"
                    ],
                    "report_artifacts": deleted_counts["report_artifacts"],
                }
                session.add(
                    ConversationDeleteIntentModel(
                        runtime_mode=runtime_mode.value,
                        conversation_id=conversation_id,
                        report_ids_json=json.dumps(
                            report_ids,
                            ensure_ascii=True,
                            separators=(",", ":"),
                        ),
                        deleted_counts_json=json.dumps(
                            ordered_counts,
                            ensure_ascii=True,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
                )
                await session.flush()
        return RepositoryDeleteResult(
            deleted_counts=ordered_counts, report_ids=report_ids
        )

    @staticmethod
    def _delete_result_from_intent(
        intent: ConversationDeleteIntentModel,
    ) -> RepositoryDeleteResult:
        try:
            report_ids = json.loads(intent.report_ids_json)
            deleted_counts = json.loads(intent.deleted_counts_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ConversationHistoryCorruptionError(
                "conversation_delete_intent_invalid"
            ) from exc
        expected_keys = {
            "work_memories",
            "result_snapshots",
            "pending_clarifications",
            "report_artifacts",
        }
        if (
            not isinstance(report_ids, list)
            or any(not isinstance(report_id, str) for report_id in report_ids)
            or not isinstance(deleted_counts, dict)
            or set(deleted_counts) != expected_keys
            or any(
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
                for count in deleted_counts.values()
            )
        ):
            raise ConversationHistoryCorruptionError(
                "conversation_delete_intent_invalid"
            )
        return RepositoryDeleteResult(
            deleted_counts=deleted_counts,
            report_ids=report_ids,
        )

    async def complete_delete(
        self, runtime_mode: RuntimeDataMode, conversation_id: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(ConversationDeleteIntentModel).where(
                        and_(
                            ConversationDeleteIntentModel.runtime_mode
                            == runtime_mode.value,
                            ConversationDeleteIntentModel.conversation_id
                            == conversation_id,
                        )
                    )
                )
