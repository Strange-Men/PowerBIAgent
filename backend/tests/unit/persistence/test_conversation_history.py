"""M4.3 conversation history/search SQLite integration tests.

These tests deliberately exercise the real async SQLite repositories.  They
freeze the namespace-first contract before the API/service implementation:
conversation identity is ``(runtime_mode, conversation_id)`` and linked report
identity is ``(source_mode, conversation_id)``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.application.conversation_history_service import (
    ConversationHistoryService,
    InvalidConversationCursorError,
)
from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.conversation.models import ConversationNotFoundError
from backend.app.memory.models import MemoryStatus, RuntimeDataMode, StructuredWorkMemory
from backend.app.memory.result_snapshot import ReportResultSnapshot, TurnResultSnapshot
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import (
    Base,
    ConversationModel,
    PendingClarificationModel,
    ReportArtifactModel,
    ReportDeleteIntentModel,
    ReportPresentationModel,
    ResultSnapshotModel,
    WorkMemoryModel,
)
from backend.app.persistence.repositories.conversation_history import (
    SQLiteConversationHistoryRepository,
)
from backend.app.persistence.repositories.report_artifact import (
    SQLiteReportArtifactRepository,
)
from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
from backend.app.persistence.serialization import domain_to_json
from backend.app.report.resources import (
    LocalReportRepository,
    ReportArtifact,
    ReportArtifactMetadata,
    ReportNotFoundError,
    ReportSpec,
    ReportStorageError,
)


UTC_BASE = datetime(2026, 8, 20, 10, 0, 0)


@dataclass
class HistoryEnvironment:
    db_path: Path
    engine: object
    session_factory: async_sessionmaker[AsyncSession]
    repository: SQLiteConversationHistoryRepository
    snapshot_repository: SQLiteSnapshotRepository


@pytest_asyncio.fixture
async def history_env(tmp_path: Path):
    db_path = tmp_path / "history.db"
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(db_path),
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await configure_engine(engine)
    session_factory = create_session_factory(engine)
    env = HistoryEnvironment(
        db_path=db_path,
        engine=engine,
        session_factory=session_factory,
        repository=SQLiteConversationHistoryRepository(session_factory),
        snapshot_repository=SQLiteSnapshotRepository(session_factory),
    )
    yield env
    await dispose_engine(engine)


async def _insert_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    mode: RuntimeDataMode,
    conversation_id: str,
    created_at: datetime,
    updated_at: datetime,
    archived_at: datetime | None = None,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                ConversationModel(
                    conversation_id=conversation_id,
                    runtime_mode=mode.value,
                    created_at=created_at,
                    updated_at=updated_at,
                    archived_at=archived_at,
                )
            )


def _snapshot(
    *,
    mode: RuntimeDataMode,
    conversation_id: str,
    request_id: str,
    answer: str | None = None,
    clarification: str | None = None,
    report_html: str | None = None,
) -> TurnResultSnapshot:
    if report_html is not None:
        response_type = "report"
        report = ReportResultSnapshot(
            report_id=f"rpt_{hashlib.sha256(request_id.encode()).hexdigest()[:32]}",
            template_key="sales_report",
            html=report_html,
        )
    elif clarification is not None:
        response_type = "clarification"
        report = None
    else:
        response_type = "answer"
        report = None
        answer = answer or "stored answer"
    return TurnResultSnapshot(
        request_id=request_id,
        conversation_id=conversation_id,
        intent="data_question",
        response_type=response_type,
        terminal_state="completed" if response_type != "clarification" else "clarification",
        answer=answer if response_type == "answer" else None,
        report=report,
        clarification_question=clarification,
        memory_commit=response_type in {"answer", "report"},
        final_memory_version=1 if response_type in {"answer", "report"} else None,
        is_mock=mode == RuntimeDataMode.MOCK,
        source_mode=mode.value,
        request_fingerprint_hash=hashlib.sha256(request_id.encode()).hexdigest(),
    )


async def _insert_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot: TurnResultSnapshot,
    *,
    mode: RuntimeDataMode,
    created_at: datetime,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                ResultSnapshotModel(
                    request_id=snapshot.request_id,
                    runtime_mode=mode.value,
                    conversation_id=snapshot.conversation_id,
                    request_fingerprint_hash=snapshot.request_fingerprint_hash,
                    terminal_state=snapshot.terminal_state,
                    response_type=snapshot.response_type,
                    payload_json=domain_to_json(snapshot),
                    created_at=created_at,
                )
            )


async def _insert_committed_memory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    mode: RuntimeDataMode,
    conversation_id: str,
    request_id: str,
    analysis_goal: str,
    created_at: datetime,
) -> None:
    memory = StructuredWorkMemory(
        conversation_id=conversation_id,
        request_id=request_id,
        semantic_model_key="stored_model",
        current_intent="data_question",
        analysis_goal=analysis_goal,
        state_status=MemoryStatus.COMMITTED,
        runtime_mode=mode,
        is_mock=mode == RuntimeDataMode.MOCK,
        base_memory_version=0,
        memory_version=1,
        created_at=created_at,
        updated_at=created_at,
    )
    async with session_factory() as session:
        async with session.begin():
            session.add(
                WorkMemoryModel(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    runtime_mode=mode.value,
                    state_status=MemoryStatus.COMMITTED.value,
                    base_memory_version=0,
                    memory_version=1,
                    semantic_model_key="stored_model",
                    current_intent="data_question",
                    analysis_goal=analysis_goal,
                    payload_json=domain_to_json(memory),
                    created_at=created_at,
                    updated_at=created_at,
                )
            )


async def _seed_turn(
    env: HistoryEnvironment,
    *,
    mode: RuntimeDataMode,
    conversation_id: str,
    request_id: str,
    when: datetime,
    answer: str,
    analysis_goal: str,
) -> None:
    await _insert_snapshot(
        env.session_factory,
        _snapshot(
            mode=mode,
            conversation_id=conversation_id,
            request_id=request_id,
            answer=answer,
        ),
        mode=mode,
        created_at=when,
    )
    await _insert_committed_memory(
        env.session_factory,
        mode=mode,
        conversation_id=conversation_id,
        request_id=request_id,
        analysis_goal=analysis_goal,
        created_at=when,
    )


async def _conversation_row(
    env: HistoryEnvironment,
    mode: RuntimeDataMode,
    conversation_id: str,
) -> ConversationModel | None:
    async with env.session_factory() as session:
        result = await session.execute(
            select(ConversationModel).where(
                and_(
                    ConversationModel.runtime_mode == mode.value,
                    ConversationModel.conversation_id == conversation_id,
                )
            )
        )
        return result.scalar_one_or_none()


class TestRecentConversations:
    @pytest.mark.asyncio
    async def test_first_snapshot_message_sets_title_and_restorable_transcript(
        self, history_env: HistoryEnvironment
    ) -> None:
        snapshot = _snapshot(
            mode=RuntimeDataMode.REAL,
            conversation_id="m53-test-title",
            request_id="m53-test-title-request",
            answer="stored answer",
        ).model_copy(update={"user_message": "  查看八月各区域销售表现  "})

        await history_env.snapshot_repository.save(snapshot, RuntimeDataMode.REAL)
        recent = await history_env.repository.list_recent(
            RuntimeDataMode.REAL, limit=20, after=None
        )
        history = await history_env.repository.get_history(
            RuntimeDataMode.REAL,
            "m53-test-title",
            limit=20,
            after=None,
        )

        assert recent.items[0].title == "查看八月各区域销售表现"
        assert history.title == "查看八月各区域销售表现"
        assert history.items[0].user_message == "  查看八月各区域销售表现  "

    @pytest.mark.asyncio
    async def test_recent_order_is_deterministic_with_stable_tie_breaker(
        self, history_env: HistoryEnvironment
    ) -> None:
        for conversation_id, created_at, updated_at in (
            ("conv-z", UTC_BASE, UTC_BASE + timedelta(minutes=2)),
            ("conv-a", UTC_BASE + timedelta(seconds=1), UTC_BASE + timedelta(minutes=2)),
            ("conv-b", UTC_BASE + timedelta(seconds=1), UTC_BASE + timedelta(minutes=2)),
            ("conv-c", UTC_BASE + timedelta(minutes=3), UTC_BASE + timedelta(minutes=1)),
        ):
            await _insert_conversation(
                history_env.session_factory,
                mode=RuntimeDataMode.MOCK,
                conversation_id=conversation_id,
                created_at=created_at,
                updated_at=updated_at,
            )

        service = ConversationHistoryService(history_env.repository)
        first = await service.list_recent(RuntimeDataMode.MOCK, limit=2)
        assert [item.conversation_id for item in first.items] == ["conv-b", "conv-a"]
        assert first.next_cursor

        second = await service.list_recent(
            RuntimeDataMode.MOCK, limit=2, cursor=first.next_cursor
        )
        assert [item.conversation_id for item in second.items] == ["conv-z", "conv-c"]
        assert second.next_cursor is None

    @pytest.mark.asyncio
    async def test_all_35_conversations_are_pageable_with_stable_total_count(
        self, history_env: HistoryEnvironment
    ) -> None:
        async with history_env.session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        ConversationModel(
                            conversation_id=f"full-history-{index:02d}",
                            runtime_mode=RuntimeDataMode.REAL.value,
                        )
                        for index in range(35)
                    ]
                )

        service = ConversationHistoryService(history_env.repository)
        seen: list[str] = []
        cursor: str | None = None
        page_sizes: list[int] = []
        while True:
            page = await service.list_recent(
                RuntimeDataMode.REAL,
                limit=12,
                cursor=cursor,
            )
            assert page.total_count == 35
            page_sizes.append(len(page.items))
            seen.extend(item.conversation_id for item in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert page_sizes == [12, 12, 11]
        assert len(seen) == len(set(seen)) == 35

    @pytest.mark.asyncio
    async def test_completed_snapshot_touches_conversation_activity_time(
        self, history_env: HistoryEnvironment
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-touch",
            created_at=datetime(2000, 1, 1),
            updated_at=datetime(2000, 1, 1),
        )
        await history_env.snapshot_repository.save(
            _snapshot(
                mode=RuntimeDataMode.MOCK,
                conversation_id="conv-touch",
                request_id="req-touch",
                answer="activity",
            ),
            RuntimeDataMode.MOCK,
        )
        row = await _conversation_row(
            history_env, RuntimeDataMode.MOCK, "conv-touch"
        )
        assert row is not None
        assert row.updated_at > datetime(2000, 1, 1)


class TestNamespaceAndHistory:
    @pytest.mark.asyncio
    async def test_same_conversation_id_isolated_in_recent_and_history(
        self, history_env: HistoryEnvironment
    ) -> None:
        for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
            await _insert_conversation(
                history_env.session_factory,
                mode=mode,
                conversation_id="shared-conv",
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
            await _seed_turn(
                history_env,
                mode=mode,
                conversation_id="shared-conv",
                request_id=f"req-{mode.value}",
                when=UTC_BASE,
                answer=f"{mode.value} answer",
                analysis_goal=f"用户提问: {mode.value} question",
            )

        service = ConversationHistoryService(history_env.repository)
        mock_recent = await service.list_recent(RuntimeDataMode.MOCK, limit=20)
        real_recent = await service.list_recent(RuntimeDataMode.REAL, limit=20)
        assert [(x.runtime_mode, x.conversation_id) for x in mock_recent.items] == [
            (RuntimeDataMode.MOCK, "shared-conv")
        ]
        assert [(x.runtime_mode, x.conversation_id) for x in real_recent.items] == [
            (RuntimeDataMode.REAL, "shared-conv")
        ]

        mock_history = await service.get_history(
            RuntimeDataMode.MOCK, "shared-conv", limit=20
        )
        real_history = await service.get_history(
            RuntimeDataMode.REAL, "shared-conv", limit=20
        )
        assert [x.answer for x in mock_history.items] == ["mock answer"]
        assert [x.answer for x in real_history.items] == ["real answer"]
        assert mock_history.items[0].memory.analysis_goal == "用户提问: mock question"
        assert real_history.items[0].memory.analysis_goal == "用户提问: real question"

    @pytest.mark.asyncio
    async def test_history_survives_repository_restart(
        self, history_env: HistoryEnvironment
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-restart-history",
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        await _seed_turn(
            history_env,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-restart-history",
            request_id="req-restart-history",
            when=UTC_BASE,
            answer="persisted answer",
            analysis_goal="用户提问: persisted question",
        )

        await dispose_engine(history_env.engine)
        restarted_engine = create_engine(
            Settings(
                persistence_backend=PersistenceBackend.SQLITE,
                persistence_database_path=str(history_env.db_path),
            ),
            echo=False,
        )
        await configure_engine(restarted_engine)
        try:
            restarted = ConversationHistoryService(
                SQLiteConversationHistoryRepository(
                    create_session_factory(restarted_engine)
                )
            )
            page = await restarted.get_history(
                RuntimeDataMode.MOCK, "conv-restart-history", limit=20
            )
            assert len(page.items) == 1
            assert page.items[0].request_id == "req-restart-history"
            assert page.items[0].answer == "persisted answer"
        finally:
            await dispose_engine(restarted_engine)

    @pytest.mark.asyncio
    async def test_history_pagination_is_deterministic(
        self, history_env: HistoryEnvironment
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-history-page",
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        for request_id in ("req-a", "req-b", "req-c"):
            await _insert_snapshot(
                history_env.session_factory,
                _snapshot(
                    mode=RuntimeDataMode.MOCK,
                    conversation_id="conv-history-page",
                    request_id=request_id,
                    answer=request_id,
                ),
                mode=RuntimeDataMode.MOCK,
                created_at=UTC_BASE,
            )

        service = ConversationHistoryService(history_env.repository)
        first = await service.get_history(
            RuntimeDataMode.MOCK, "conv-history-page", limit=2
        )
        second = await service.get_history(
            RuntimeDataMode.MOCK,
            "conv-history-page",
            limit=2,
            cursor=first.next_cursor,
        )
        assert [x.request_id for x in first.items] == ["req-c", "req-b"]
        assert [x.request_id for x in second.items] == ["req-a"]


class TestReportHistory:
    @pytest.mark.asyncio
    async def test_report_history_is_source_mode_scoped(
        self, history_env: HistoryEnvironment
    ) -> None:
        metadata_repo = SQLiteReportArtifactRepository(history_env.session_factory)
        for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
            await _insert_conversation(
                history_env.session_factory,
                mode=mode,
                conversation_id="shared-report-conv",
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
            report_repo = LocalReportRepository(
                root=history_env.db_path.parent / f"reports-{mode.value}",
                metadata_repo=metadata_repo,
            )
            await report_repo.store(
                ReportSpec(
                    title=f"{mode.value} report",
                    template_key="sales_report",
                    summary="stored",
                    source_mode=mode.value,
                    contract_version="1.0",
                    semantic_model_key=f"{mode.value}_model",
                    schema_fingerprint=("a" if mode == RuntimeDataMode.MOCK else "b") * 64,
                    verified_fact_set_ids=[f"fact-{mode.value}"],
                    query_result_ids=[f"query-{mode.value}"],
                ),
                "<!DOCTYPE html><html><body>stored</body></html>",
                conversation_id="shared-report-conv",
                request_id=f"req-report-{mode.value}",
            )

        service = ConversationHistoryService(history_env.repository)
        mock_reports = await service.list_reports(
            RuntimeDataMode.MOCK, "shared-report-conv", limit=20
        )
        real_reports = await service.list_reports(
            RuntimeDataMode.REAL, "shared-report-conv", limit=20
        )
        assert [x.source_mode for x in mock_reports.items] == ["mock"]
        assert [x.source_mode for x in real_reports.items] == ["real"]
        assert mock_reports.items[0].semantic_model_key == "mock_model"
        assert real_reports.items[0].semantic_model_key == "real_model"

    @pytest.mark.asyncio
    async def test_all_30_reports_are_pageable_and_archive_is_recoverable(
        self, history_env: HistoryEnvironment
    ) -> None:
        conversation_id = "full-report-history"
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.REAL,
            conversation_id=conversation_id,
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        metadata_repo = SQLiteReportArtifactRepository(history_env.session_factory)
        report_repo = LocalReportRepository(
            history_env.db_path.parent / "full-report-history",
            metadata_repo,
        )
        reports_root = history_env.db_path.parent / "full-report-history"
        reports_root.mkdir(parents=True, exist_ok=True)
        report_ids: list[str] = []
        async with history_env.session_factory() as session:
            async with session.begin():
                for index in range(30):
                    report_id = f"rpt_{index:032x}"
                    request_id = f"report-request-{index}"
                    html = f"<!DOCTYPE html><html><body>{index}</body></html>"
                    artifact = ReportArtifact(
                        report_id=report_id,
                        template_key="sales_report",
                        html="",
                        source_mode="real",
                        generated_at=UTC_BASE,
                        contract_version="1.0",
                        semantic_model_key="model",
                        schema_fingerprint=f"{index:064x}",
                        verified_fact_set_ids=[f"fact-{index}"],
                        query_result_ids=[f"query-{index}"],
                        content_hash=hashlib.sha256(html.encode()).hexdigest(),
                        created_at=UTC_BASE + timedelta(seconds=index),
                        view_reference=f"/api/reports/{report_id}",
                        download_reference=f"/api/reports/{report_id}/download",
                        relative_path=f"{report_id}.html",
                        conversation_id=conversation_id,
                        request_id=request_id,
                    )
                    metadata = ReportArtifactMetadata.from_domain(
                        artifact,
                        f"{report_id}.html",
                        conversation_id=conversation_id,
                        request_id=request_id,
                    )
                    session.add(
                        ReportArtifactModel(
                            report_id=report_id,
                            conversation_id=conversation_id,
                            request_id=request_id,
                            template_key="sales_report",
                            semantic_model_key="model",
                            schema_fingerprint=f"{index:064x}",
                            source_mode="real",
                            content_hash=artifact.content_hash,
                            relative_path=f"{report_id}.html",
                            payload_json=domain_to_json(metadata),
                        )
                    )
                    session.add(
                        ReportPresentationModel(
                            report_id=report_id,
                            source_mode="real",
                            conversation_id=conversation_id,
                            request_id=request_id,
                            display_title=f"report {index}",
                            availability_status="available",
                            created_at=artifact.created_at,
                            updated_at=artifact.created_at,
                        )
                    )
                    (reports_root / f"{report_id}.html").write_text(
                        html, encoding="utf-8"
                    )
                    report_ids.append(report_id)

        service = ConversationHistoryService(history_env.repository)
        seen: list[str] = []
        cursor: str | None = None
        while True:
            page = await service.list_managed_reports(
                RuntimeDataMode.REAL,
                status="active",
                limit=13,
                cursor=cursor,
            )
            assert page.total_count == 30
            assert page.status == "active"
            seen.extend(item.report_id for item in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert len(seen) == len(set(seen)) == 30

        active_cursor = (
            await service.list_managed_reports(
                RuntimeDataMode.REAL, status="active", limit=1
            )
        ).next_cursor
        assert active_cursor is not None
        with pytest.raises(InvalidConversationCursorError):
            await service.list_managed_reports(
                RuntimeDataMode.REAL,
                status="archived",
                limit=1,
                cursor=active_cursor,
            )

        original, original_html = await report_repo.read_html(report_ids[0])
        archived = await report_repo.archive(report_ids[0], "real")
        assert archived.archived_at is not None
        active_page = await service.list_managed_reports(
            RuntimeDataMode.REAL, status="active", limit=30
        )
        archived_page = await service.list_managed_reports(
            RuntimeDataMode.REAL, status="archived", limit=30
        )
        assert active_page.total_count == 29
        assert [item.report_id for item in archived_page.items] == [report_ids[0]]
        unchanged, unchanged_html = await report_repo.read_html(report_ids[0])
        assert unchanged.content_hash == original.content_hash
        assert unchanged_html == original_html

        restored = await report_repo.restore(report_ids[0], "real")
        assert restored.restored is True
        assert (
            await service.list_managed_reports(
                RuntimeDataMode.REAL, status="archived", limit=30
            )
        ).total_count == 0

    @pytest.mark.asyncio
    async def test_report_rename_and_delete_preserve_presentation_tombstone(
        self, history_env: HistoryEnvironment
    ) -> None:
        conversation_id = "conv-report-delete"
        request_id = "req-report-delete"
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.REAL,
            conversation_id=conversation_id,
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        metadata_repo = SQLiteReportArtifactRepository(history_env.session_factory)
        reports_root = history_env.db_path.parent / "reports-delete"
        report_repo = LocalReportRepository(
            root=reports_root, metadata_repo=metadata_repo
        )
        artifact = await report_repo.store(
            ReportSpec(
                title="sales report",
                template_key="sales_report",
                summary="stored",
                source_mode="real",
                contract_version="1.0",
                semantic_model_key="model",
                schema_fingerprint="f" * 64,
                verified_fact_set_ids=["fact"],
                query_result_ids=["query"],
            ),
            "<!DOCTYPE html><html><body>delete report</body></html>",
            conversation_id=conversation_id,
            request_id=request_id,
        )
        snapshot = _snapshot(
            mode=RuntimeDataMode.REAL,
            conversation_id=conversation_id,
            request_id=request_id,
            report_html="<!DOCTYPE html><html><body>legacy ignored</body></html>",
        ).model_copy(
            update={
                "report": ReportResultSnapshot(
                    report_id=artifact.report_id,
                    template_key=artifact.template_key,
                    contract_version=artifact.contract_version,
                    view_reference=artifact.view_reference,
                    download_reference=artifact.download_reference,
                    content_type=artifact.content_type,
                    content_hash=artifact.content_hash,
                )
            }
        )
        await _insert_snapshot(
            history_env.session_factory,
            snapshot,
            mode=RuntimeDataMode.REAL,
            created_at=UTC_BASE,
        )
        service = ConversationHistoryService(history_env.repository)
        before = await service.get_history(
            RuntimeDataMode.REAL, conversation_id, limit=20
        )
        assert before.items[0].report is not None
        original_hash = artifact.content_hash
        _, original_html = await report_repo.read_html(artifact.report_id)

        renamed = await report_repo.rename(artifact.report_id, "区域销售报告")
        assert renamed.display_title == "区域销售报告"
        unchanged, unchanged_html = await report_repo.read_html(artifact.report_id)
        assert unchanged.content_hash == original_hash
        assert unchanged_html == original_html
        renamed_history = await service.get_history(
            RuntimeDataMode.REAL, conversation_id, limit=20
        )
        assert renamed_history.items[0].report.display_title == "区域销售报告"
        listed = await service.list_reports(
            RuntimeDataMode.REAL, conversation_id, limit=20
        )
        assert listed.items[0].display_title == "区域销售报告"

        await report_repo.archive(artifact.report_id, "real")
        archived_reports = await service.list_managed_reports(
            RuntimeDataMode.REAL, status="archived", limit=20
        )
        assert archived_reports.items[0].display_title == "区域销售报告"

        deleted = await report_repo.delete(artifact.report_id)
        assert deleted.conversation_id == conversation_id
        assert not (reports_root / f"{artifact.report_id}.html").exists()
        with pytest.raises(ReportNotFoundError):
            await metadata_repo.get(artifact.report_id)
        history = await service.get_history(
            RuntimeDataMode.REAL, conversation_id, limit=20
        )
        tombstone = history.items[0].report
        assert tombstone is not None
        assert tombstone.display_title == "区域销售报告"
        assert tombstone.availability_status == "deleted"
        assert tombstone.view_reference == ""
        assert tombstone.download_reference == ""
        assert tombstone.content_hash == ""
        assert history.conversation_id == conversation_id

    @pytest.mark.asyncio
    async def test_report_delete_failure_is_durable_and_retryable(
        self, history_env: HistoryEnvironment, monkeypatch
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-report-delete-failure",
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        metadata_repo = SQLiteReportArtifactRepository(history_env.session_factory)
        reports_root = history_env.db_path.parent / "reports-delete-failure"
        report_repo = LocalReportRepository(reports_root, metadata_repo)
        artifact = await report_repo.store(
            ReportSpec(
                title="report", template_key="test_report", source_mode="mock"
            ),
            "<!DOCTYPE html><html><body>retry</body></html>",
            conversation_id="conv-report-delete-failure",
            request_id="req-report-delete-failure",
        )
        target = reports_root / f"{artifact.report_id}.html"
        original_unlink = Path.unlink

        def fail_unlink(self, *args, **kwargs):
            if self == target:
                raise OSError("injected unlink failure")
            return original_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(ReportStorageError, match="report_artifact_delete_failed"):
            await report_repo.delete(artifact.report_id)
        assert target.exists()
        async with history_env.session_factory() as session:
            pending = await session.scalar(
                select(ReportDeleteIntentModel).where(
                    ReportDeleteIntentModel.report_id == artifact.report_id
                )
            )
            assert pending is not None

        monkeypatch.setattr(Path, "unlink", original_unlink)
        await report_repo.delete(artifact.report_id)
        assert not target.exists()
        async with history_env.session_factory() as session:
            pending = await session.scalar(
                select(ReportDeleteIntentModel).where(
                    ReportDeleteIntentModel.report_id == artifact.report_id
                )
            )
            assert pending is None

    @pytest.mark.asyncio
    async def test_history_never_projects_another_conversation_report(
        self, history_env: HistoryEnvironment
    ) -> None:
        for conversation_id in ("conv-owner-a", "conv-owner-b"):
            await _insert_conversation(
                history_env.session_factory,
                mode=RuntimeDataMode.REAL,
                conversation_id=conversation_id,
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
        metadata_repo = SQLiteReportArtifactRepository(history_env.session_factory)
        report_repo = LocalReportRepository(
            history_env.db_path.parent / "reports-owner", metadata_repo
        )
        artifact = await report_repo.store(
            ReportSpec(
                title="A report",
                template_key="sales_report",
                source_mode="real",
                contract_version="1.0",
                semantic_model_key="model",
                schema_fingerprint="a" * 64,
                verified_fact_set_ids=["fact"],
                query_result_ids=["query"],
            ),
            "<!DOCTYPE html><html><body>A</body></html>",
            conversation_id="conv-owner-a",
            request_id="req-owner-a",
        )
        forged_b_snapshot = _snapshot(
            mode=RuntimeDataMode.REAL,
            conversation_id="conv-owner-b",
            request_id="req-owner-b",
            report_html="<!DOCTYPE html><html><body>B</body></html>",
        ).model_copy(
            update={
                "report": ReportResultSnapshot(
                    report_id=artifact.report_id,
                    template_key=artifact.template_key,
                )
            }
        )
        await _insert_snapshot(
            history_env.session_factory,
            forged_b_snapshot,
            mode=RuntimeDataMode.REAL,
            created_at=UTC_BASE,
        )
        history = await ConversationHistoryService(
            history_env.repository
        ).get_history(RuntimeDataMode.REAL, "conv-owner-b", limit=20)
        assert history.items[0].report is None


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_is_namespace_scoped(
        self, history_env: HistoryEnvironment
    ) -> None:
        for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
            await _insert_conversation(
                history_env.session_factory,
                mode=mode,
                conversation_id=f"conv-search-{mode.value}",
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
            await _seed_turn(
                history_env,
                mode=mode,
                conversation_id=f"conv-search-{mode.value}",
                request_id=f"req-search-{mode.value}",
                when=UTC_BASE,
                answer="needle answer",
                analysis_goal="用户提问: needle question",
            )

        service = ConversationHistoryService(history_env.repository)
        mock = await service.search(
            RuntimeDataMode.MOCK, query="needle", limit=20
        )
        real = await service.search(
            RuntimeDataMode.REAL, query="needle", limit=20
        )
        assert [x.conversation_id for x in mock.items] == ["conv-search-mock"]
        assert [x.conversation_id for x in real.items] == ["conv-search-real"]

    @pytest.mark.asyncio
    async def test_search_only_uses_declared_stored_fields_not_report_html(
        self, history_env: HistoryEnvironment
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-no-fabrication",
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        await _insert_snapshot(
            history_env.session_factory,
            _snapshot(
                mode=RuntimeDataMode.MOCK,
                conversation_id="conv-no-fabrication",
                request_id="req-report-html",
                report_html="<!DOCTYPE html><html><body>html-only-secret-term</body></html>",
            ),
            mode=RuntimeDataMode.MOCK,
            created_at=UTC_BASE,
        )
        service = ConversationHistoryService(history_env.repository)
        page = await service.search(
            RuntimeDataMode.MOCK, query="html-only-secret-term", limit=20
        )
        assert page.items == []

    @pytest.mark.asyncio
    async def test_search_pagination_and_restart_are_stable(
        self, history_env: HistoryEnvironment
    ) -> None:
        for conversation_id in ("conv-b", "conv-a", "conv-c"):
            await _insert_conversation(
                history_env.session_factory,
                mode=RuntimeDataMode.MOCK,
                conversation_id=conversation_id,
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
            await _seed_turn(
                history_env,
                mode=RuntimeDataMode.MOCK,
                conversation_id=conversation_id,
                request_id=f"req-{conversation_id}",
                when=UTC_BASE,
                answer="stable needle",
                analysis_goal="用户提问: stable needle",
            )
        service = ConversationHistoryService(history_env.repository)
        first = await service.search(
            RuntimeDataMode.MOCK, query="needle", limit=2
        )
        restarted = ConversationHistoryService(
            SQLiteConversationHistoryRepository(history_env.session_factory)
        )
        second = await restarted.search(
            RuntimeDataMode.MOCK,
            query="needle",
            limit=2,
            cursor=first.next_cursor,
        )
        assert [x.conversation_id for x in first.items] == ["conv-c", "conv-b"]
        assert [x.conversation_id for x in second.items] == ["conv-a"]


class TestArchiveDeleteAndErrors:
    @pytest.mark.asyncio
    async def test_failed_resource_survives_restart_and_full_lifecycle(
        self, history_env: HistoryEnvironment
    ) -> None:
        service = ConversationHistoryService(history_env.repository)
        failed = await service.record_failed(
            RuntimeDataMode.REAL,
            "failed-resource",
            title="失败的销售问题",
            error_type="client_request_failed",
        )
        assert failed.resource_status == "failed"

        restarted = ConversationHistoryService(
            SQLiteConversationHistoryRepository(history_env.session_factory)
        )
        recent = await restarted.list_recent(RuntimeDataMode.REAL, limit=20)
        assert len(recent.items) == 1
        assert recent.items[0].resource_status == "failed"
        assert recent.items[0].last_error_type == "client_request_failed"

        renamed = await restarted.rename(
            RuntimeDataMode.REAL, "failed-resource", "可管理的失败会话"
        )
        assert renamed.title == "可管理的失败会话"
        await restarted.archive(RuntimeDataMode.REAL, "failed-resource")
        archived = await restarted.list_archived(RuntimeDataMode.REAL, limit=20)
        assert archived.items[0].resource_status == "failed"
        await restarted.restore(RuntimeDataMode.REAL, "failed-resource")
        restored = await restarted.list_recent(RuntimeDataMode.REAL, limit=20)
        assert restored.items[0].resource_status == "failed"
        deleted = await restarted.delete(RuntimeDataMode.REAL, "failed-resource")
        assert deleted.deleted is True
        assert (
            await restarted.list_recent(RuntimeDataMode.REAL, limit=20)
        ).items == []

    @pytest.mark.asyncio
    async def test_failed_snapshot_sets_formal_resource_metadata_without_memory_commit(
        self, history_env: HistoryEnvironment
    ) -> None:
        snapshot = _snapshot(
            mode=RuntimeDataMode.REAL,
            conversation_id="failed-snapshot",
            request_id="failed-request",
            answer=None,
        ).model_copy(
            update={
                "terminal_state": "tool_failed",
                "response_type": "",
                "error_type": "powerbi_query_failed",
                "memory_commit": False,
            }
        )
        await history_env.snapshot_repository.save(snapshot, RuntimeDataMode.REAL)

        item = (
            await ConversationHistoryService(history_env.repository).list_recent(
                RuntimeDataMode.REAL, limit=20
            )
        ).items[0]
        assert item.resource_status == "failed"
        assert item.last_error_type == "powerbi_query_failed"
        history = await ConversationHistoryService(
            history_env.repository
        ).get_history(RuntimeDataMode.REAL, "failed-snapshot", limit=20)
        assert history.items[0].memory_commit is False

    @pytest.mark.asyncio
    async def test_archive_and_delete_affect_one_namespace_only(
        self, history_env: HistoryEnvironment
    ) -> None:
        for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
            await _insert_conversation(
                history_env.session_factory,
                mode=mode,
                conversation_id="shared-delete",
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
            await _seed_turn(
                history_env,
                mode=mode,
                conversation_id="shared-delete",
                request_id=f"req-delete-{mode.value}",
                when=UTC_BASE,
                answer=f"delete {mode.value}",
                analysis_goal=f"用户提问: delete {mode.value}",
            )

        service = ConversationHistoryService(history_env.repository)
        archived = await service.archive(RuntimeDataMode.MOCK, "shared-delete")
        assert archived.runtime_mode == RuntimeDataMode.MOCK
        assert archived.archived_at is not None
        assert (await service.list_recent(RuntimeDataMode.MOCK, limit=20)).items == []
        assert [
            x.conversation_id
            for x in (await service.list_recent(RuntimeDataMode.REAL, limit=20)).items
        ] == ["shared-delete"]
        archived_history = await service.get_history(
            RuntimeDataMode.MOCK, "shared-delete", limit=20
        )
        assert [x.answer for x in archived_history.items] == ["delete mock"]

        deleted = await service.delete(RuntimeDataMode.MOCK, "shared-delete")
        assert deleted.deleted is True
        with pytest.raises(ConversationNotFoundError):
            await service.get_history(RuntimeDataMode.MOCK, "shared-delete", limit=20)
        real_history = await service.get_history(
            RuntimeDataMode.REAL, "shared-delete", limit=20
        )
        assert [x.answer for x in real_history.items] == ["delete real"]

    @pytest.mark.asyncio
    async def test_archive_list_and_restore_preserve_history(
        self, history_env: HistoryEnvironment
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-restore",
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        await _seed_turn(
            history_env,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-restore",
            request_id="req-restore",
            when=UTC_BASE,
            answer="preserved",
            analysis_goal="用户提问: preserve",
        )
        service = ConversationHistoryService(history_env.repository)
        await service.archive(RuntimeDataMode.MOCK, "conv-restore")
        assert (await service.list_recent(RuntimeDataMode.MOCK, limit=20)).items == []
        archived = await service.list_archived(RuntimeDataMode.MOCK, limit=20)
        assert [item.conversation_id for item in archived.items] == ["conv-restore"]
        restored = await service.restore(RuntimeDataMode.MOCK, "conv-restore")
        assert restored.restored is True
        recent = await service.list_recent(RuntimeDataMode.MOCK, limit=20)
        assert [item.conversation_id for item in recent.items] == ["conv-restore"]
        history = await service.get_history(
            RuntimeDataMode.MOCK, "conv-restore", limit=20
        )
        assert history.items[0].answer == "preserved"

    @pytest.mark.asyncio
    async def test_delete_removes_only_linked_namespace_report_html(
        self, history_env: HistoryEnvironment
    ) -> None:
        for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
            await _insert_conversation(
                history_env.session_factory,
                mode=mode,
                conversation_id="shared-files",
                created_at=UTC_BASE,
                updated_at=UTC_BASE,
            )
        metadata_repo = SQLiteReportArtifactRepository(history_env.session_factory)
        reports_root = history_env.db_path.parent / "reports"
        report_repo = LocalReportRepository(root=reports_root, metadata_repo=metadata_repo)
        report_ids: dict[RuntimeDataMode, str] = {}
        for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
            artifact = await report_repo.store(
                ReportSpec(
                    title="delete report",
                    template_key="sales_report",
                    summary="stored",
                    source_mode=mode.value,
                    contract_version="1.0",
                    semantic_model_key="model",
                    schema_fingerprint="f" * 64,
                    verified_fact_set_ids=["fact"],
                    query_result_ids=["query"],
                ),
                "<!DOCTYPE html><html><body>delete me</body></html>",
                conversation_id="shared-files",
                request_id=f"req-files-{mode.value}",
            )
            report_ids[mode] = artifact.report_id

        service = ConversationHistoryService(
            history_env.repository, report_repository=report_repo
        )
        await service.delete(RuntimeDataMode.MOCK, "shared-files")
        assert not (reports_root / f"{report_ids[RuntimeDataMode.MOCK]}.html").exists()
        assert (reports_root / f"{report_ids[RuntimeDataMode.REAL]}.html").exists()
        real_reports = await service.list_reports(
            RuntimeDataMode.REAL, "shared-files", limit=20
        )
        assert [x.report_id for x in real_reports.items] == [
            report_ids[RuntimeDataMode.REAL]
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["history", "reports", "archive", "delete"])
    async def test_unknown_conversation_fails_consistently(
        self, history_env: HistoryEnvironment, operation: str
    ) -> None:
        service = ConversationHistoryService(history_env.repository)
        with pytest.raises(ConversationNotFoundError):
            if operation == "history":
                await service.get_history(RuntimeDataMode.MOCK, "missing", limit=20)
            elif operation == "reports":
                await service.list_reports(RuntimeDataMode.MOCK, "missing", limit=20)
            elif operation == "archive":
                await service.archive(RuntimeDataMode.MOCK, "missing")
            else:
                await service.delete(RuntimeDataMode.MOCK, "missing")

    @pytest.mark.asyncio
    async def test_cursor_is_bound_to_namespace_query_and_resource(
        self, history_env: HistoryEnvironment
    ) -> None:
        await _insert_conversation(
            history_env.session_factory,
            mode=RuntimeDataMode.MOCK,
            conversation_id="conv-cursor",
            created_at=UTC_BASE,
            updated_at=UTC_BASE,
        )
        service = ConversationHistoryService(history_env.repository)
        page = await service.list_recent(RuntimeDataMode.MOCK, limit=1)
        assert page.next_cursor is None
        with pytest.raises(InvalidConversationCursorError):
            await service.list_recent(
                RuntimeDataMode.REAL, limit=1, cursor="not-a-valid-cursor"
            )


@pytest.mark.asyncio
async def test_delete_cascades_all_sqlite_child_rows(
    history_env: HistoryEnvironment,
) -> None:
    await _insert_conversation(
        history_env.session_factory,
        mode=RuntimeDataMode.MOCK,
        conversation_id="conv-cascade",
        created_at=UTC_BASE,
        updated_at=UTC_BASE,
    )
    await _seed_turn(
        history_env,
        mode=RuntimeDataMode.MOCK,
        conversation_id="conv-cascade",
        request_id="req-cascade",
        when=UTC_BASE,
        answer="cascade",
        analysis_goal="用户提问: cascade",
    )
    async with history_env.session_factory() as session:
        async with session.begin():
            session.add(
                PendingClarificationModel(
                    conversation_id="conv-cascade",
                    runtime_mode="mock",
                    chain_id="chain-cascade",
                    semantic_model_key="model",
                    schema_fingerprint="a" * 64,
                    payload_json="{}",
                )
            )

    service = ConversationHistoryService(history_env.repository)
    result = await service.delete(RuntimeDataMode.MOCK, "conv-cascade")
    assert result.deleted_counts == {
        "work_memories": 1,
        "result_snapshots": 1,
        "pending_clarifications": 1,
        "report_artifacts": 0,
    }
    async with history_env.session_factory() as session:
        for model in (
            ConversationModel,
            WorkMemoryModel,
            ResultSnapshotModel,
            PendingClarificationModel,
            ReportArtifactModel,
        ):
            result_rows = await session.execute(select(model))
            assert result_rows.scalars().all() == []
