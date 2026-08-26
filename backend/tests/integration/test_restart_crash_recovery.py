"""Restart/crash acceptance for the local SQLite + report filesystem runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.application.conversation_history_service import (
    ConversationHistoryService,
)
from backend.app.application.deepseek_turn_service import DeepSeekTurnService
from backend.app.application.mock_turn_service import MockTurnService
from backend.app.config.settings import (
    LLMMode,
    PersistenceBackend,
    PowerBIMode,
    Settings,
)
from backend.app.conversation.models import ConversationNotFoundError
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse
from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
)
from backend.app.memory.result_snapshot import (
    IdempotencyClaimStatus,
    TurnResultSnapshot,
)
from backend.app.persistence.database import (
    configure_engine,
    create_engine,
    create_session_factory,
    dispose_engine,
)
from backend.app.persistence.models import (
    Base,
    ConversationDeleteIntentModel,
    ConversationModel,
    ReportArtifactModel,
    ResultSnapshotModel,
    WorkMemoryModel,
)
from backend.app.persistence.repositories.conversation_history import (
    SQLiteConversationHistoryRepository,
)
from backend.app.persistence.repositories.common import PersistenceRepositoryError
from backend.app.persistence.repositories.memory import SQLiteMemoryRepository
from backend.app.persistence.repositories.report_artifact import (
    SQLiteReportArtifactRepository,
)
from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer
from backend.app.report.resources import (
    LocalReportRepository,
    ReportNotFoundError,
    ReportSpec,
    ReportStorageError,
)
from backend.app.schemas.data_contracts import (
    DAXRequest,
    PowerBIError,
    QueryResult,
    SemanticModelSchema,
    TimeRangeMode,
    TimeRangeSpec,
)


class _FailIfCalledLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_mock(self) -> bool:
        return False

    async def generate(
        self, request: LLMRequest, output_type: type[BaseModel]
    ) -> LLMResponse:
        self.call_count += 1
        raise AssertionError("corrupt committed Memory reached the LLM")


class _FailIfCalledPowerBIAdapter(PowerBIAdapter):
    def __init__(self) -> None:
        self.schema_calls = 0
        self.dax_calls = 0

    @property
    def provider_name(self) -> str:
        return "local_mcp"

    @property
    def is_mock(self) -> bool:
        return False

    async def health_check(self) -> bool:
        raise AssertionError("corrupt committed Memory reached Power BI health")

    async def get_semantic_model_schema(
        self, semantic_model_key: str
    ) -> SemanticModelSchema:
        self.schema_calls += 1
        raise AssertionError("corrupt committed Memory queried Power BI schema")

    async def execute_dax(self, request: DAXRequest) -> QueryResult:
        self.dax_calls += 1
        raise AssertionError("corrupt committed Memory executed DAX")

    async def normalize_result(self, raw: object) -> QueryResult:
        raise AssertionError("corrupt committed Memory normalized a result")

    async def normalize_error(self, raw: object) -> PowerBIError:
        raise AssertionError("corrupt committed Memory normalized an error")


async def _create_database(db_path: Path) -> None:
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(db_path),
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await configure_engine(engine)
    await dispose_engine(engine)


async def _open_runtime(
    db_path: Path,
) -> tuple[object, async_sessionmaker[AsyncSession], ConversationHistoryService, LocalReportRepository]:
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=str(db_path),
    )
    engine = create_engine(settings, echo=False)
    await configure_engine(engine)
    session_factory = create_session_factory(engine)
    report_repository = LocalReportRepository(
        root=db_path.parent / "reports",
        metadata_repo=SQLiteReportArtifactRepository(session_factory),
    )
    service = ConversationHistoryService(
        SQLiteConversationHistoryRepository(session_factory),
        report_repository=report_repository,
    )
    return engine, session_factory, service, report_repository


def _turn_service(
    session_factory: async_sessionmaker[AsyncSession],
    report_repository: LocalReportRepository,
) -> MockTurnService:
    return MockTurnService(
        memory_repo=SQLiteMemoryRepository(session_factory),
        snapshot_store=SQLiteSnapshotRepository(session_factory),
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
        report_repository=report_repository,
    )


async def _insert_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    runtime_mode: RuntimeDataMode,
    conversation_id: str,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                ConversationModel(
                    runtime_mode=runtime_mode.value,
                    conversation_id=conversation_id,
                )
            )


def _report_spec(source_mode: RuntimeDataMode) -> ReportSpec:
    return ReportSpec(
        title="Crash recovery report",
        template_key="sales_report",
        summary="Stored before delete crash",
        source_mode=source_mode.value,
        contract_version="1.0",
        semantic_model_key="restart_model",
        schema_fingerprint="a" * 64,
        verified_fact_set_ids=["fact-restart"],
        query_result_ids=["query-restart"],
    )


def _commit_evidence(runtime_mode: RuntimeDataMode) -> MemoryCommitEvidence:
    return MemoryCommitEvidence(
        intent_valid=True,
        request_allowed=True,
        query_plan_valid=True,
        dax_valid=True,
        tool_execution_succeeded=True,
        query_result_valid=True,
        response_valid=True,
        runtime_mode=runtime_mode,
    )


def _pending_memory(
    *,
    runtime_mode: RuntimeDataMode,
    conversation_id: str,
    request_id: str,
    base_version: int,
) -> StructuredWorkMemory:
    return StructuredWorkMemory(
        runtime_mode=runtime_mode,
        is_mock=runtime_mode == RuntimeDataMode.MOCK,
        conversation_id=conversation_id,
        request_id=request_id,
        semantic_model_key="restart_model",
        current_intent="data_question",
        analysis_goal=f"用户提问: {request_id}",
        measures=["Total Sales"],
        llm_provider="mock" if runtime_mode == RuntimeDataMode.MOCK else "deepseek",
        powerbi_provider=(
            "mock_powerbi"
            if runtime_mode == RuntimeDataMode.MOCK
            else "local_powerbi_mcp"
        ),
        base_memory_version=base_version,
        memory_version=0,
    )


@pytest.mark.asyncio
async def test_valid_committed_payload_restores_full_semantic_state_after_restart(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "complete-memory-payload.db"
    await _create_database(db_path)
    conversation_id = "complete-memory-payload-conversation"
    request_id = "req-complete-memory-payload"

    engine1, sf1, _, _ = await _open_runtime(db_path)
    memory1 = SQLiteMemoryRepository(sf1)
    pending = _pending_memory(
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id=conversation_id,
        request_id=request_id,
        base_version=0,
    )
    pending.dimensions = ["Category"]
    pending.filters = [{
        "field": "Category",
        "operator": "eq",
        "value": "Electronics",
    }]
    pending.time_range = TimeRangeSpec(
        date_field="OrderDate",
        start_date="2026-01-01",
        end_date="2026-06-30",
        mode=TimeRangeMode.EXPLICIT_RANGE,
        grain="month",
    )
    pending.sort = "desc"
    pending.top_n = 5
    pending.last_query_plan = {
        "semantic_model_key": "restart_model",
        "measures": ["Total Sales"],
        "dimensions": ["Category"],
        "filters": pending.filters,
        "sort": "desc",
        "top_n": 5,
    }
    pending.last_dax = "EVALUATE ROW(\"Total Sales\", [Total Sales])"
    pending.last_query_result_id = "result-complete-payload"
    pending.last_report_id = "report-complete-payload"
    await memory1.create_pending(pending, RuntimeDataMode.MOCK)
    await memory1.commit(pending, _commit_evidence(RuntimeDataMode.MOCK))
    await dispose_engine(engine1)

    engine2, sf2, _, _ = await _open_runtime(db_path)
    try:
        recovered = await SQLiteMemoryRepository(sf2).get_latest_committed(
            conversation_id, RuntimeDataMode.MOCK
        )
        assert recovered is not None
        assert recovered.memory_version == 1
        assert recovered.dimensions == pending.dimensions
        assert recovered.filters == pending.filters
        assert recovered.time_range == pending.time_range
        assert recovered.sort == pending.sort
        assert recovered.top_n == pending.top_n
        assert recovered.last_query_plan == pending.last_query_plan
        assert recovered.last_dax == pending.last_dax
        assert recovered.last_query_result_id == pending.last_query_result_id
        assert recovered.last_report_id == pending.last_report_id
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_committed_memory_row_payload_namespace_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory-row-payload-namespace-mismatch.db"
    await _create_database(db_path)
    conversation_id = "memory-row-payload-namespace-conversation"
    request_id = "req-memory-row-payload-namespace"

    engine1, sf1, _, _ = await _open_runtime(db_path)
    memory1 = SQLiteMemoryRepository(sf1)
    seed = _pending_memory(
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id=conversation_id,
        request_id=request_id,
        base_version=0,
    )
    await memory1.create_pending(seed, RuntimeDataMode.MOCK)
    await memory1.commit(seed, _commit_evidence(RuntimeDataMode.MOCK))
    async with sf1() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(WorkMemoryModel).where(
                        and_(
                            WorkMemoryModel.request_id == request_id,
                            WorkMemoryModel.runtime_mode
                            == RuntimeDataMode.MOCK.value,
                        )
                    )
                )
            ).scalar_one()
            payload = json.loads(row.payload_json)
            payload["runtime_mode"] = RuntimeDataMode.REAL.value
            await session.execute(
                update(WorkMemoryModel)
                .where(WorkMemoryModel.id == row.id)
                .values(payload_json=json.dumps(payload, ensure_ascii=False))
            )
    await dispose_engine(engine1)

    engine2, sf2, _, _ = await _open_runtime(db_path)
    try:
        with pytest.raises(
            PersistenceRepositoryError,
            match="work_memory_row_payload_mismatch:runtime_mode",
        ):
            await SQLiteMemoryRepository(sf2).get_latest_committed(
                conversation_id, RuntimeDataMode.MOCK
            )
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("corrupt_payload", "expected_error", "error_match"),
    [
        (None, PersistenceRepositoryError, "work_memory_payload_missing"),
        ("", PersistenceRepositoryError, "work_memory_payload_missing"),
        ("{malformed-json", json.JSONDecodeError, None),
        ("{}", PersistenceRepositoryError, "work_memory_payload_incomplete"),
    ],
    ids=["null", "empty", "malformed-json", "incomplete-json"],
)
async def test_missing_or_malformed_committed_payload_fails_closed_after_restart(
    tmp_path: Path,
    corrupt_payload: str | None,
    expected_error: type[Exception],
    error_match: str | None,
) -> None:
    db_path = tmp_path / f"corrupt-memory-payload-{corrupt_payload!r}.db"
    await _create_database(db_path)
    conversation_id = "corrupt-memory-payload-conversation"
    seed_request_id = "req-corrupt-memory-payload-seed"
    next_request_id = "req-after-memory-payload-corruption"

    engine1, sf1, _, _ = await _open_runtime(db_path)
    memory1 = SQLiteMemoryRepository(sf1)
    seed = _pending_memory(
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id=conversation_id,
        request_id=seed_request_id,
        base_version=0,
    )
    seed.filters = [{
        "field": "Category",
        "operator": "eq",
        "value": "Electronics",
    }]
    seed.top_n = 5
    await memory1.create_pending(seed, RuntimeDataMode.MOCK)
    await memory1.commit(seed, _commit_evidence(RuntimeDataMode.MOCK))
    async with sf1() as session:
        async with session.begin():
            await session.execute(
                update(WorkMemoryModel)
                .where(
                    and_(
                        WorkMemoryModel.request_id == seed_request_id,
                        WorkMemoryModel.runtime_mode == RuntimeDataMode.MOCK.value,
                    )
                )
                .values(payload_json=corrupt_payload)
            )
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    service = _turn_service(sf2, reports2)
    service.llm_provider.generate = AsyncMock(
        side_effect=AssertionError("corrupt committed Memory reached Mock LLM")
    )
    service.powerbi.get_semantic_model_schema = AsyncMock(
        side_effect=AssertionError("corrupt committed Memory queried schema")
    )
    service.powerbi.execute_dax = AsyncMock(
        side_effect=AssertionError("corrupt committed Memory executed DAX")
    )
    service.tool_gateway = service._build_tool_gateway()

    try:
        raises_kwargs = {"match": error_match} if error_match else {}
        with pytest.raises(expected_error, **raises_kwargs):
            await service.execute(
                message="继续分析",
                conversation_id=conversation_id,
                request_id=next_request_id,
            )

        assert service.llm_provider.generate.await_count == 0
        assert service.powerbi.get_semantic_model_schema.await_count == 0
        assert service.powerbi.execute_dax.await_count == 0
        memory2 = SQLiteMemoryRepository(sf2)
        assert await memory2.get_by_request_id(
            next_request_id, RuntimeDataMode.MOCK
        ) is None
        assert await SQLiteSnapshotRepository(sf2).get(
            next_request_id, RuntimeDataMode.MOCK
        ) is None
        async with sf2() as session:
            rows = (
                await session.execute(
                    select(WorkMemoryModel).where(
                        and_(
                            WorkMemoryModel.conversation_id == conversation_id,
                            WorkMemoryModel.runtime_mode
                            == RuntimeDataMode.MOCK.value,
                        )
                    )
                )
            ).scalars().all()
        assert [
            (row.request_id, row.memory_version, row.state_status) for row in rows
        ] == [(seed_request_id, 1, MemoryStatus.COMMITTED.value)]
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime_mode", [RuntimeDataMode.MOCK, RuntimeDataMode.REAL]
)
async def test_corrupt_committed_filter_fails_closed_after_restart_before_execution(
    tmp_path: Path,
    runtime_mode: RuntimeDataMode,
) -> None:
    db_path = tmp_path / f"corrupt-filter-{runtime_mode.value}.db"
    await _create_database(db_path)
    conversation_id = "shared-corrupt-filter-conversation"
    seed_request_id = f"req-corrupt-seed-{runtime_mode.value}"
    next_request_id = f"req-after-corruption-{runtime_mode.value}"
    sibling_mode = (
        RuntimeDataMode.REAL
        if runtime_mode == RuntimeDataMode.MOCK
        else RuntimeDataMode.MOCK
    )

    engine1, sf1, _, _ = await _open_runtime(db_path)
    memory1 = SQLiteMemoryRepository(sf1)
    corrupt_seed = _pending_memory(
        runtime_mode=runtime_mode,
        conversation_id=conversation_id,
        request_id=seed_request_id,
        base_version=0,
    )
    corrupt_seed.filters = [{
        "field": "Category",
        "operator": "eq",
        "value": "Electronics",
    }]
    await memory1.create_pending(corrupt_seed, runtime_mode)
    await memory1.commit(corrupt_seed, _commit_evidence(runtime_mode))

    sibling = _pending_memory(
        runtime_mode=sibling_mode,
        conversation_id=conversation_id,
        request_id=f"req-valid-sibling-{sibling_mode.value}",
        base_version=0,
    )
    sibling.filters = [{
        "field": "Category",
        "operator": "eq",
        "value": "Furniture",
    }]
    await memory1.create_pending(sibling, sibling_mode)
    await memory1.commit(sibling, _commit_evidence(sibling_mode))

    async with sf1() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(WorkMemoryModel).where(
                        and_(
                            WorkMemoryModel.request_id == seed_request_id,
                            WorkMemoryModel.runtime_mode == runtime_mode.value,
                        )
                    )
                )
            ).scalar_one()
            payload = json.loads(row.payload_json)
            payload["filters"] = [{"operator": "eq"}]
            await session.execute(
                update(WorkMemoryModel)
                .where(
                    and_(
                        WorkMemoryModel.request_id == seed_request_id,
                        WorkMemoryModel.runtime_mode == runtime_mode.value,
                    )
                )
                .values(payload_json=json.dumps(payload, ensure_ascii=False))
            )
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    llm_provider: _FailIfCalledLLMProvider | None = None
    real_adapter: _FailIfCalledPowerBIAdapter | None = None
    mock_llm_generate: AsyncMock | None = None
    if runtime_mode == RuntimeDataMode.MOCK:
        service = _turn_service(sf2, reports2)
        mock_llm_generate = AsyncMock(
            side_effect=AssertionError("corrupt committed Memory reached Mock LLM")
        )
        service.llm_provider.generate = mock_llm_generate
        service.powerbi.get_semantic_model_schema = AsyncMock(
            side_effect=AssertionError(
                "corrupt committed Memory queried Mock Power BI schema"
            )
        )
        service.powerbi.execute_dax = AsyncMock(
            side_effect=AssertionError(
                "corrupt committed Memory executed Mock DAX"
            )
        )
        service.tool_gateway = service._build_tool_gateway()
    else:
        llm_provider = _FailIfCalledLLMProvider()
        real_adapter = _FailIfCalledPowerBIAdapter()
        settings = Settings(
            _env_file=None,
            llm_mode=LLMMode.DEEPSEEK,
            powerbi_mode=PowerBIMode.LOCAL_MCP,
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=str(db_path),
            deepseek_api_key="test-key-not-real",
            powerbi_local_semantic_model_key="restart_model",
        )
        service = DeepSeekTurnService(
            memory_repo=SQLiteMemoryRepository(sf2),
            llm_provider=llm_provider,
            powerbi_adapter=real_adapter,
            report_renderer=MockReportRenderer(),
            settings=settings,
            report_repository=reports2,
            snapshot_store=SQLiteSnapshotRepository(sf2),
        )

    try:
        for _ in range(2):
            with pytest.raises(
                ValidationError, match="committed_memory_filter_invalid"
            ):
                await asyncio.wait_for(
                    service.execute(
                        message="继续分析",
                        conversation_id=conversation_id,
                        request_id=next_request_id,
                        semantic_model_key="restart_model",
                    ),
                    timeout=1,
                )

        if runtime_mode == RuntimeDataMode.MOCK:
            assert mock_llm_generate is not None
            assert mock_llm_generate.await_count == 0
            assert service.powerbi.get_semantic_model_schema.await_count == 0
            assert service.powerbi.execute_dax.await_count == 0
        else:
            assert llm_provider is not None
            assert real_adapter is not None
            assert llm_provider.call_count == 0
            assert real_adapter.schema_calls == 0
            assert real_adapter.dax_calls == 0

        valid_sibling = await SQLiteMemoryRepository(sf2).get_latest_committed(
            conversation_id, sibling_mode
        )
        assert valid_sibling is not None
        assert valid_sibling.memory_version == 1
        assert valid_sibling.filters == [{
            "field": "Category",
            "operator": "eq",
            "value": "Furniture",
        }]

        async with sf2() as session:
            rows = (
                await session.execute(
                    select(WorkMemoryModel).where(
                        and_(
                            WorkMemoryModel.conversation_id == conversation_id,
                            WorkMemoryModel.runtime_mode == runtime_mode.value,
                        )
                    )
                )
            ).scalars().all()
        assert [(row.request_id, row.memory_version, row.state_status) for row in rows] == [
            (seed_request_id, 1, MemoryStatus.COMMITTED.value)
        ]
        assert all(row.request_id != next_request_id for row in rows)
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_committed_memory_and_snapshot_replay_survive_real_restart(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory-snapshot-restart.db"
    await _create_database(db_path)
    conversation_id = "shared-restart-conversation"
    request_id = "req-completed-before-restart"
    message = "本月销售额是多少？"

    engine1, sf1, _, reports1 = await _open_runtime(db_path)
    memory1 = SQLiteMemoryRepository(sf1)
    service1 = _turn_service(sf1, reports1)
    completed = await service1.execute(
        message=message,
        conversation_id=conversation_id,
        request_id=request_id,
    )
    assert completed["terminal_state"] == "completed"
    assert completed["final_memory_version"] == 1

    pending = _pending_memory(
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id=conversation_id,
        request_id="req-pending-at-crash",
        base_version=1,
    )
    failed = _pending_memory(
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id=conversation_id,
        request_id="req-failed-before-crash",
        base_version=1,
    )
    await memory1.create_pending(pending, RuntimeDataMode.MOCK)
    await memory1.create_pending(failed, RuntimeDataMode.MOCK)
    await memory1.mark_failed(
        failed.request_id,
        RuntimeDataMode.MOCK,
        reason="injected failure",
        stage="acceptance",
    )

    real_memory = _pending_memory(
        runtime_mode=RuntimeDataMode.REAL,
        conversation_id=conversation_id,
        request_id="req-real-same-conversation",
        base_version=0,
    )
    await memory1.create_pending(real_memory, RuntimeDataMode.REAL)
    await memory1.commit(real_memory, _commit_evidence(RuntimeDataMode.REAL))
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    try:
        memory2 = SQLiteMemoryRepository(sf2)
        mock_latest = await memory2.get_latest_committed(
            conversation_id, RuntimeDataMode.MOCK
        )
        real_latest = await memory2.get_latest_committed(
            conversation_id, RuntimeDataMode.REAL
        )
        assert mock_latest is not None
        assert mock_latest.request_id == request_id
        assert mock_latest.memory_version == 1
        assert real_latest is not None
        assert real_latest.request_id == "req-real-same-conversation"
        assert real_latest.memory_version == 1
        mock_rows = await memory2.list_by_conversation(
            conversation_id, runtime_mode=RuntimeDataMode.MOCK
        )
        assert {row.request_id: row.state_status for row in mock_rows} == {
            request_id: MemoryStatus.COMMITTED,
            "req-pending-at-crash": MemoryStatus.PENDING,
            "req-failed-before-crash": MemoryStatus.FAILED,
        }

        service2 = _turn_service(sf2, reports2)
        service2.powerbi.get_semantic_model_schema = AsyncMock(
            side_effect=AssertionError("snapshot replay queried schema")
        )
        service2.powerbi.execute_dax = AsyncMock(
            side_effect=AssertionError("snapshot replay executed DAX")
        )
        service2.tool_gateway = service2._build_tool_gateway()
        replay = await service2.execute(
            message=message,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        assert replay["idempotent_replay"] is True
        assert replay["replayed_request_id"] == request_id
        assert replay["answer"] == completed["answer"]
        assert service2.powerbi.get_semantic_model_schema.await_count == 0
        assert service2.powerbi.execute_dax.await_count == 0

        with pytest.raises(IdempotencyConflictError):
            await service2.execute(
                message="换一个不同问题",
                conversation_id=conversation_id,
                request_id=request_id,
            )
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_terminal_snapshot_row_payload_mismatch_fails_closed_on_replay(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "snapshot-row-payload-mismatch.db"
    await _create_database(db_path)
    conversation_id = "snapshot-row-payload-conversation"
    request_id = "req-snapshot-row-payload"
    message = "本月销售额是多少？"

    engine1, sf1, _, reports1 = await _open_runtime(db_path)
    completed = await _turn_service(sf1, reports1).execute(
        message=message,
        conversation_id=conversation_id,
        request_id=request_id,
    )
    assert completed["terminal_state"] == "completed"
    async with sf1() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(ResultSnapshotModel).where(
                        and_(
                            ResultSnapshotModel.request_id == request_id,
                            ResultSnapshotModel.runtime_mode
                            == RuntimeDataMode.MOCK.value,
                        )
                    )
                )
            ).scalar_one()
            payload = json.loads(row.payload_json)
            payload["conversation_id"] = "wrong-conversation"
            await session.execute(
                update(ResultSnapshotModel)
                .where(ResultSnapshotModel.id == row.id)
                .values(payload_json=json.dumps(payload, ensure_ascii=False))
            )
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    try:
        service2 = _turn_service(sf2, reports2)
        service2.powerbi.get_semantic_model_schema = AsyncMock(
            side_effect=AssertionError("corrupt snapshot replay queried schema")
        )
        service2.powerbi.execute_dax = AsyncMock(
            side_effect=AssertionError("corrupt snapshot replay executed DAX")
        )
        service2.tool_gateway = service2._build_tool_gateway()

        with pytest.raises(
            PersistenceRepositoryError,
            match="result_snapshot_row_payload_mismatch:conversation_id",
        ):
            await service2.execute(
                message=message,
                conversation_id=conversation_id,
                request_id=request_id,
            )
        assert service2.powerbi.get_semantic_model_schema.await_count == 0
        assert service2.powerbi.execute_dax.await_count == 0
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_process_local_inflight_loss_never_creates_completed_snapshot(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "inflight-crash.db"
    await _create_database(db_path)
    engine1, sf1, _, _ = await _open_runtime(db_path)
    snapshots1 = SQLiteSnapshotRepository(sf1)
    claimed, _ = await snapshots1.claim(
        "req-inflight-crash", RuntimeDataMode.MOCK, "a" * 64
    )
    assert claimed == IdempotencyClaimStatus.OWNER
    await dispose_engine(engine1)

    engine2, sf2, _, _ = await _open_runtime(db_path)
    try:
        snapshots2 = SQLiteSnapshotRepository(sf2)
        assert (
            await snapshots2.get("req-inflight-crash", RuntimeDataMode.MOCK)
            is None
        )
        reclaimed, _ = await snapshots2.claim(
            "req-inflight-crash", RuntimeDataMode.MOCK, "b" * 64
        )
        assert reclaimed == IdempotencyClaimStatus.OWNER
        async with sf2() as session:
            rows = await session.execute(select(ResultSnapshotModel))
            assert rows.scalars().all() == []
        await snapshots2.abort("req-inflight-crash", RuntimeDataMode.MOCK)
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_snapshot_saved_before_tracker_complete_replays_after_restart(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "snapshot-save-crash.db"
    await _create_database(db_path)
    request = {
        "message": "本月销售额是多少？",
        "conversation_id": "conv-snapshot-save-crash",
        "request_id": "req-snapshot-save-crash",
    }

    engine1, sf1, _, reports1 = await _open_runtime(db_path)
    service1 = _turn_service(sf1, reports1)
    service1.pipeline.snapshot_store.complete = AsyncMock(
        side_effect=SystemExit("crash after snapshot save")
    )
    with pytest.raises(SystemExit, match="crash after snapshot save"):
        await service1.execute(**request)
    stored = await SQLiteSnapshotRepository(sf1).get(
        request["request_id"], RuntimeDataMode.MOCK
    )
    assert stored is not None
    assert stored.terminal_state == "completed"
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    try:
        service2 = _turn_service(sf2, reports2)
        service2.powerbi.execute_dax = AsyncMock(
            side_effect=AssertionError("durable snapshot was re-executed")
        )
        service2.tool_gateway = service2._build_tool_gateway()
        replay = await service2.execute(**request)
        assert replay["idempotent_replay"] is True
        assert replay["answer"] == stored.answer
        assert service2.powerbi.execute_dax.await_count == 0
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_memory_without_terminal_snapshot_fails_closed_after_restart(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "partial-turn-crash.db"
    await _create_database(db_path)
    request = {
        "message": "本月销售额是多少？",
        "conversation_id": "conv-partial-turn-crash",
        "request_id": "req-partial-turn-crash",
    }

    engine1, sf1, _, _ = await _open_runtime(db_path)
    memory1 = SQLiteMemoryRepository(sf1)
    partial = _pending_memory(
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id=request["conversation_id"],
        request_id=request["request_id"],
        base_version=0,
    )
    await memory1.create_pending(partial, RuntimeDataMode.MOCK)
    claimed, _ = await SQLiteSnapshotRepository(sf1).claim(
        request["request_id"], RuntimeDataMode.MOCK, "a" * 64
    )
    assert claimed == IdempotencyClaimStatus.OWNER
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    try:
        service2 = _turn_service(sf2, reports2)
        with pytest.raises(
            IdempotencyCoordinationError,
            match="incomplete persisted request",
        ):
            await service2.execute(**request)
        assert (
            await SQLiteSnapshotRepository(sf2).get(
                request["request_id"], RuntimeDataMode.MOCK
            )
            is None
        )
        persisted = await SQLiteMemoryRepository(sf2).get_by_request_id(
            request["request_id"], RuntimeDataMode.MOCK
        )
        assert persisted is not None
        assert persisted.state_status == MemoryStatus.PENDING
    finally:
        await dispose_engine(engine2)


@pytest.mark.asyncio
async def test_report_replay_after_restart_uses_filesystem_authority_and_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "report-restart.db"
    await _create_database(db_path)
    request = {
        "message": "生成销售周报",
        "conversation_id": "conv-report-restart",
        "request_id": "req-report-restart",
        "report_template_key": "sales_report",
    }

    engine1, sf1, _, reports1 = await _open_runtime(db_path)
    service1 = _turn_service(sf1, reports1)
    first = await service1.execute(**request)
    assert first["terminal_state"] == "completed"
    report_id = first["report"]["report_id"]
    first_html = first["report"]["html"]
    html_path = reports1.root / f"{report_id}.html"
    assert html_path.exists()
    async with sf1() as session:
        stored_snapshot = (
            await session.execute(
                select(ResultSnapshotModel).where(
                    ResultSnapshotModel.request_id == request["request_id"]
                )
            )
        ).scalar_one()
        snapshot_payload = json.loads(stored_snapshot.payload_json)
        assert snapshot_payload["report"]["html"] == ""
    await dispose_engine(engine1)

    engine2, sf2, _, reports2 = await _open_runtime(db_path)
    service2 = _turn_service(sf2, reports2)
    artifact, recovered_html = await reports2.read_html(report_id)
    assert artifact.content_hash == hashlib.sha256(
        first_html.encode("utf-8")
    ).hexdigest()
    assert recovered_html == first_html
    replay = await service2.execute(**request)
    assert replay["idempotent_replay"] is True
    assert replay["report"]["html"] == first_html

    html_path.unlink()
    with pytest.raises(ReportNotFoundError):
        await service2.execute(**request)
    html_path.write_bytes(first_html.encode("utf-8"))
    html_path.write_bytes(
        b"<!DOCTYPE html><html><body>tampered</body></html>"
    )
    with pytest.raises(ReportStorageError, match="report_content_hash_mismatch"):
        await service2.execute(**request)

    html_path.write_bytes(first_html.encode("utf-8"))
    async with sf2() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(ReportArtifactModel).where(
                        ReportArtifactModel.report_id == report_id
                    )
                )
            ).scalar_one()
            mismatched_payload = json.loads(row.payload_json)
            mismatched_payload["conversation_id"] = "wrong-conversation"
            await session.execute(
                update(ReportArtifactModel)
                .where(ReportArtifactModel.report_id == report_id)
                .values(
                    conversation_id="wrong-conversation",
                    payload_json=json.dumps(
                        mismatched_payload,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
    await dispose_engine(engine2)

    engine3, sf3, _, reports3 = await _open_runtime(db_path)
    service3 = _turn_service(sf3, reports3)
    with pytest.raises(ReportStorageError, match="report_snapshot_artifact_mismatch"):
        await service3.execute(**request)
    async with sf3() as session:
        async with session.begin():
            await session.execute(
                update(ReportArtifactModel)
                .where(ReportArtifactModel.report_id == report_id)
                .values(payload_json="{}")
            )
    await dispose_engine(engine3)

    engine4, _, _, reports4 = await _open_runtime(db_path)
    try:
        with pytest.raises(ReportStorageError):
            await reports4.read_html(report_id)
    finally:
        await dispose_engine(engine4)


async def _seed_namespace(
    session_factory: async_sessionmaker[AsyncSession],
    report_repository: LocalReportRepository,
    *,
    runtime_mode: RuntimeDataMode,
    conversation_id: str,
) -> tuple[str, str, Path]:
    request_id = f"req-history-{runtime_mode.value}"
    memory_repository = SQLiteMemoryRepository(session_factory)
    memory = _pending_memory(
        runtime_mode=runtime_mode,
        conversation_id=conversation_id,
        request_id=request_id,
        base_version=0,
    )
    await memory_repository.create_pending(memory, runtime_mode)
    committed = await memory_repository.commit(
        memory, _commit_evidence(runtime_mode)
    )
    assert committed.memory_version == 1

    artifact = await report_repository.store(
        _report_spec(runtime_mode),
        (
            "<!DOCTYPE html><html><body>"
            f"{runtime_mode.value} namespace report"
            "</body></html>"
        ),
        conversation_id=conversation_id,
        request_id=request_id,
    )
    snapshot = TurnResultSnapshot(
        request_id=request_id,
        conversation_id=conversation_id,
        intent="data_question",
        response_type="answer",
        terminal_state="completed",
        answer=f"restart searchable {runtime_mode.value} answer",
        memory_commit=True,
        final_memory_version=1,
        is_mock=runtime_mode == RuntimeDataMode.MOCK,
        source_mode=runtime_mode.value,
        request_fingerprint_hash=hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest(),
    )
    await SQLiteSnapshotRepository(session_factory).save(snapshot, runtime_mode)
    return request_id, artifact.report_id, (
        report_repository.root / f"{artifact.report_id}.html"
    )


@pytest.mark.asyncio
async def test_history_archive_delete_and_namespace_isolation_survive_restart(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "history-lifecycle-restart.db"
    await _create_database(db_path)
    conversation_id = "shared-history-restart"

    engine1, sf1, history1, reports1 = await _open_runtime(db_path)
    seeded: dict[RuntimeDataMode, tuple[str, str, Path]] = {}
    for mode in (RuntimeDataMode.MOCK, RuntimeDataMode.REAL):
        seeded[mode] = await _seed_namespace(
            sf1,
            reports1,
            runtime_mode=mode,
            conversation_id=conversation_id,
        )

    await history1.archive(RuntimeDataMode.MOCK, conversation_id)
    before_restart = {
        "mock_recent": (
            await history1.list_recent(RuntimeDataMode.MOCK, limit=20)
        ).model_dump(mode="json"),
        "real_recent": (
            await history1.list_recent(RuntimeDataMode.REAL, limit=20)
        ).model_dump(mode="json"),
        "mock_history": (
            await history1.get_history(
                RuntimeDataMode.MOCK, conversation_id, limit=20
            )
        ).model_dump(mode="json"),
        "real_history": (
            await history1.get_history(
                RuntimeDataMode.REAL, conversation_id, limit=20
            )
        ).model_dump(mode="json"),
        "mock_search": (
            await history1.search(
                RuntimeDataMode.MOCK, query="restart searchable", limit=20
            )
        ).model_dump(mode="json"),
        "real_search": (
            await history1.search(
                RuntimeDataMode.REAL, query="restart searchable", limit=20
            )
        ).model_dump(mode="json"),
        "mock_reports": (
            await history1.list_reports(
                RuntimeDataMode.MOCK, conversation_id, limit=20
            )
        ).model_dump(mode="json"),
        "real_reports": (
            await history1.list_reports(
                RuntimeDataMode.REAL, conversation_id, limit=20
            )
        ).model_dump(mode="json"),
    }
    assert before_restart["mock_recent"]["items"] == []
    assert before_restart["mock_search"]["items"] == []
    assert len(before_restart["mock_history"]["items"]) == 1
    assert len(before_restart["mock_reports"]["items"]) == 1
    assert len(before_restart["real_recent"]["items"]) == 1
    assert len(before_restart["real_search"]["items"]) == 1
    await dispose_engine(engine1)

    engine2, sf2, history2, _ = await _open_runtime(db_path)
    try:
        after_restart = {
            "mock_recent": (
                await history2.list_recent(RuntimeDataMode.MOCK, limit=20)
            ).model_dump(mode="json"),
            "real_recent": (
                await history2.list_recent(RuntimeDataMode.REAL, limit=20)
            ).model_dump(mode="json"),
            "mock_history": (
                await history2.get_history(
                    RuntimeDataMode.MOCK, conversation_id, limit=20
                )
            ).model_dump(mode="json"),
            "real_history": (
                await history2.get_history(
                    RuntimeDataMode.REAL, conversation_id, limit=20
                )
            ).model_dump(mode="json"),
            "mock_search": (
                await history2.search(
                    RuntimeDataMode.MOCK,
                    query="restart searchable",
                    limit=20,
                )
            ).model_dump(mode="json"),
            "real_search": (
                await history2.search(
                    RuntimeDataMode.REAL,
                    query="restart searchable",
                    limit=20,
                )
            ).model_dump(mode="json"),
            "mock_reports": (
                await history2.list_reports(
                    RuntimeDataMode.MOCK, conversation_id, limit=20
                )
            ).model_dump(mode="json"),
            "real_reports": (
                await history2.list_reports(
                    RuntimeDataMode.REAL, conversation_id, limit=20
                )
            ).model_dump(mode="json"),
        }
        assert after_restart == before_restart

        deleted = await history2.delete(RuntimeDataMode.MOCK, conversation_id)
        assert deleted.deleted_counts == {
            "work_memories": 1,
            "result_snapshots": 1,
            "pending_clarifications": 0,
            "report_artifacts": 1,
        }
        assert not seeded[RuntimeDataMode.MOCK][2].exists()
        assert seeded[RuntimeDataMode.REAL][2].exists()
        async with sf2() as session:
            intent = await session.execute(
                select(ConversationDeleteIntentModel).where(
                    and_(
                        ConversationDeleteIntentModel.runtime_mode == "mock",
                        ConversationDeleteIntentModel.conversation_id
                        == conversation_id,
                    )
                )
            )
            assert intent.scalar_one_or_none() is None
    finally:
        await dispose_engine(engine2)

    engine3, _, history3, reports3 = await _open_runtime(db_path)
    try:
        with pytest.raises(ConversationNotFoundError):
            await history3.get_history(
                RuntimeDataMode.MOCK, conversation_id, limit=20
            )
        with pytest.raises(ConversationNotFoundError):
            await history3.list_reports(
                RuntimeDataMode.MOCK, conversation_id, limit=20
            )
        real_history = await history3.get_history(
            RuntimeDataMode.REAL, conversation_id, limit=20
        )
        real_reports = await history3.list_reports(
            RuntimeDataMode.REAL, conversation_id, limit=20
        )
        assert [item.request_id for item in real_history.items] == [
            seeded[RuntimeDataMode.REAL][0]
        ]
        assert [item.report_id for item in real_reports.items] == [
            seeded[RuntimeDataMode.REAL][1]
        ]
        _, real_html = await reports3.read_html(
            seeded[RuntimeDataMode.REAL][1]
        )
        assert "real namespace report" in real_html
    finally:
        await dispose_engine(engine3)


@pytest.mark.asyncio
async def test_db_committed_html_cleanup_failure_is_retryable_after_restart(
    tmp_path: Path,
) -> None:
    """A crash after DB delete commit must retain enough intent for retry."""
    db_path = tmp_path / "delete-crash.db"
    await _create_database(db_path)

    engine1, sf1, service1, reports1 = await _open_runtime(db_path)
    await _insert_conversation(
        sf1,
        runtime_mode=RuntimeDataMode.MOCK,
        conversation_id="conv-delete-crash",
    )
    artifact = await reports1.store(
        _report_spec(RuntimeDataMode.MOCK),
        "<!DOCTYPE html><html><body>managed artifact</body></html>",
        conversation_id="conv-delete-crash",
        request_id="req-delete-crash",
    )
    html_path = reports1.root / f"{artifact.report_id}.html"
    original_unlink = Path.unlink

    def _fail_target_unlink(path: Path, *args, **kwargs):
        if path.resolve() == html_path.resolve():
            raise PermissionError("injected unlink failure")
        return original_unlink(path, *args, **kwargs)

    with patch.object(Path, "unlink", _fail_target_unlink):
        with pytest.raises(ReportStorageError, match="report_artifact_delete_failed"):
            await service1.delete(RuntimeDataMode.MOCK, "conv-delete-crash")

    assert html_path.exists()
    async with sf1() as session:
        intent = (
            await session.execute(
                select(ConversationDeleteIntentModel).where(
                    and_(
                        ConversationDeleteIntentModel.runtime_mode == "mock",
                        ConversationDeleteIntentModel.conversation_id
                        == "conv-delete-crash",
                    )
                )
            )
        ).scalar_one()
        assert json.loads(intent.report_ids_json) == [artifact.report_id]
    with pytest.raises(PersistenceRepositoryError, match="delete_pending"):
        await SQLiteMemoryRepository(sf1).create_pending(
            _pending_memory(
                runtime_mode=RuntimeDataMode.MOCK,
                conversation_id="conv-delete-crash",
                request_id="req-must-not-resurrect",
                base_version=0,
            ),
            RuntimeDataMode.MOCK,
        )
    await dispose_engine(engine1)

    engine2, sf2, service2, _ = await _open_runtime(db_path)
    try:
        retried = await service2.delete(
            RuntimeDataMode.MOCK, "conv-delete-crash"
        )
        assert retried.deleted is True
        assert retried.deleted_counts["report_artifacts"] == 1
        assert not html_path.exists()
        async with sf2() as session:
            pending_intent = await session.execute(
                select(ConversationDeleteIntentModel)
            )
            assert pending_intent.scalars().all() == []
    finally:
        await dispose_engine(engine2)
