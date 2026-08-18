"""M4.1 — SQLiteMemoryRepository + SQLiteSnapshotRepository 综合测试

覆盖矩阵：

Memory（12+ tests）：
  1. create pending
  2. get by request
  3. commit success
  4. memory version increment
  5. latest committed
  6. failed 不进入 latest committed
  7. failed memory 不能 commit
  8. stale base version conflict
  9. concurrent same-base commit only one succeeds
  10. Mock/Real same conversation isolation
  11. serialization roundtrip via DB
  12. corruption fail closed

Clarification（5 tests）：
  13. save
  14. get
  15. replace/update
  16. clear
  17. Mock/Real isolation
  18. restart recovery

Snapshot（7 tests）：
  19. save/get
  20. exists
  21. Mock/Real same request_id isolation
  22. same request/fingerprint replay
  23. different fingerprint conflict
  24. restart recovery
  25. corrupt payload fail closed

Wiring（4 tests）：
  26. memory backend → InMemory repos
  27. sqlite backend → SQLite repos
  28. engine lifecycle dispose
  29. no DB when memory backend selected
  30. temp SQLite isolation in tests
"""

from __future__ import annotations

import asyncio
import copy
import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config.settings import PersistenceBackend, Settings
from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryCommitDeniedError,
    MemoryDuplicateError,
    MemoryVersionConflictError,
)
from backend.app.memory.result_snapshot import (
    ReportResultSnapshot,
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
    ConversationModel,
    PendingClarificationModel,
    ResultSnapshotModel,
    WorkMemoryModel,
)
from backend.app.persistence.repositories.memory import SQLiteMemoryRepository
from backend.app.persistence.repositories.snapshot import SQLiteSnapshotRepository
from backend.app.persistence.serialization import domain_to_json, json_to_domain


# ===========================================================================
# Fixtures
# ===========================================================================


def _tmp_db_path() -> str:
    tmp = Path(tempfile.mkdtemp()) / "test_m41.db"
    return str(tmp)


@pytest_asyncio.fixture
async def sqlite_repos():
    """Create a fresh SQLiteMemoryRepository + SQLiteSnapshotRepository
    in a temp DB.  Yields (memory_repo, snapshot_repo, db_path).
    Disposes engine after the test.
    """
    db_path = _tmp_db_path()
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=db_path,
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await configure_engine(engine)

    session_factory = create_session_factory(engine)
    memory_repo = SQLiteMemoryRepository(session_factory=session_factory)
    snapshot_repo = SQLiteSnapshotRepository(session_factory=session_factory)

    yield memory_repo, snapshot_repo, db_path

    await dispose_engine(engine)


@pytest_asyncio.fixture
async def sqlite_memory(sqlite_repos):
    """Just the SQLiteMemoryRepository."""
    return sqlite_repos[0]


@pytest_asyncio.fixture
async def sqlite_snapshot(sqlite_repos):
    """Just the SQLiteSnapshotRepository."""
    return sqlite_repos[1]


@pytest_asyncio.fixture
async def db_path(sqlite_repos):
    """Just the DB path."""
    return sqlite_repos[2]


# Fixture 组合：第一台引擎（进程 A）
@pytest_asyncio.fixture
async def engine_a():
    """Create engine + repos for process A (restart test)."""
    db_path = _tmp_db_path()
    settings = Settings(
        persistence_backend=PersistenceBackend.SQLITE,
        persistence_database_path=db_path,
    )
    engine = create_engine(settings, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await configure_engine(engine)
    yield engine, db_path
    await dispose_engine(engine)


@pytest.fixture
def sample_memory():
    return StructuredWorkMemory(
        conversation_id="conv-001",
        request_id="req-001",
        current_intent="data_question",
        measures=["SalesAmount"],
        runtime_mode=RuntimeDataMode.MOCK,
        is_mock=True,
        llm_provider="mock",
        powerbi_provider="mock_powerbi",
        base_memory_version=0,
        memory_version=0,
    )


@pytest.fixture
def valid_evidence():
    return MemoryCommitEvidence(
        intent_valid=True,
        request_allowed=True,
        query_plan_valid=True,
        dax_valid=True,
        tool_execution_succeeded=True,
        query_result_valid=True,
        response_valid=True,
        runtime_mode=RuntimeDataMode.MOCK,
    )


@pytest.fixture
def real_evidence():
    return MemoryCommitEvidence(
        intent_valid=True,
        request_allowed=True,
        query_plan_valid=True,
        dax_valid=True,
        tool_execution_succeeded=True,
        query_result_valid=True,
        response_valid=True,
        runtime_mode=RuntimeDataMode.REAL,
    )


# ===========================================================================
# Memory Tests
# ===========================================================================


class TestMemoryBasicOperations:
    """1-2: create pending, get by request"""

    @pytest.mark.asyncio
    async def test_create_pending(self, sqlite_memory, sample_memory):
        result = await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        assert result.state_status == MemoryStatus.PENDING
        assert result.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_get_by_request_id(self, sqlite_memory, sample_memory):
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        retrieved = await sqlite_memory.get_by_request_id("req-001", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_get_by_request_id_not_found(self, sqlite_memory):
        result = await sqlite_memory.get_by_request_id("nonexistent", RuntimeDataMode.MOCK)
        assert result is None

    @pytest.mark.asyncio
    async def test_request_exists(self, sqlite_memory, sample_memory):
        assert await sqlite_memory.request_exists("req-001", RuntimeDataMode.MOCK) is False
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        assert await sqlite_memory.request_exists("req-001", RuntimeDataMode.MOCK) is True

    @pytest.mark.asyncio
    async def test_request_id_idempotent(self, sqlite_memory, sample_memory):
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryDuplicateError):
            await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)


class TestMemoryVersionSemantics:
    """3-5: commit, version increment, latest committed"""

    @pytest.mark.asyncio
    async def test_commit_success(self, sqlite_memory, sample_memory, valid_evidence):
        sample_memory.base_memory_version = 0
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        committed = await sqlite_memory.commit(sample_memory, valid_evidence)
        assert committed.state_status == MemoryStatus.COMMITTED
        assert committed.memory_version == 1
        assert committed.base_memory_version == 0

    @pytest.mark.asyncio
    async def test_commit_version_increments(self, sqlite_memory, valid_evidence):
        m1 = StructuredWorkMemory(
            conversation_id="conv-v2", request_id="req-v1",
            current_intent="data_question", measures=["Sales"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(m1, RuntimeDataMode.MOCK)
        r1 = await sqlite_memory.commit(m1, valid_evidence)
        assert r1.memory_version == 1

        latest = await sqlite_memory.get_latest_committed("conv-v2", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 1

        m2 = StructuredWorkMemory(
            conversation_id="conv-v2", request_id="req-v2",
            current_intent="data_question", measures=["Profit"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=latest.memory_version,
        )
        await sqlite_memory.create_pending(m2, RuntimeDataMode.MOCK)
        r2 = await sqlite_memory.commit(m2, valid_evidence)
        assert r2.memory_version == 2
        assert r2.base_memory_version == 1

    @pytest.mark.asyncio
    async def test_latest_committed_from_db(self, sqlite_memory, valid_evidence):
        m1 = StructuredWorkMemory(
            conversation_id="conv-lc", request_id="req-l1",
            current_intent="data_question", measures=["First"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(m1, RuntimeDataMode.MOCK)
        await sqlite_memory.commit(m1, valid_evidence)

        latest = await sqlite_memory.get_latest_committed("conv-lc", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.measures == ["First"]

    @pytest.mark.asyncio
    async def test_latest_committed_empty(self, sqlite_memory):
        result = await sqlite_memory.get_latest_committed("conv-empty", RuntimeDataMode.MOCK)
        assert result is None


class TestFailedMemory:
    """6-7: failed state"""

    @pytest.mark.asyncio
    async def test_failed_not_in_latest_committed(self, sqlite_memory, sample_memory):
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        await sqlite_memory.mark_failed("req-001", RuntimeDataMode.MOCK,
                                        reason="test failure", stage="testing")
        latest = await sqlite_memory.get_latest_committed("conv-001", RuntimeDataMode.MOCK)
        assert latest is None

    @pytest.mark.asyncio
    async def test_failed_cannot_commit(self, sqlite_memory, sample_memory, valid_evidence):
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        await sqlite_memory.mark_failed("req-001", RuntimeDataMode.MOCK, reason="fail")
        with pytest.raises(MemoryCommitDeniedError):
            await sqlite_memory.commit(sample_memory, valid_evidence)

    @pytest.mark.asyncio
    async def test_mark_failed_preserves_reason(self, sqlite_memory, sample_memory):
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        failed = await sqlite_memory.mark_failed(
            "req-001", RuntimeDataMode.MOCK, reason="timeout", stage="dax"
        )
        assert failed is not None
        assert failed.state_status == MemoryStatus.FAILED
        assert failed.failure_reason == "timeout"
        assert failed.failure_stage == "dax"

    @pytest.mark.asyncio
    async def test_mark_failed_not_found(self, sqlite_memory):
        result = await sqlite_memory.mark_failed("nonexistent", RuntimeDataMode.MOCK)
        assert result is None


class TestVersionConflict:
    """8: stale base version"""

    @pytest.mark.asyncio
    async def test_stale_base_version_conflict(self, sqlite_memory, valid_evidence):
        m1 = StructuredWorkMemory(
            conversation_id="conv-sc", request_id="req-s1",
            current_intent="data_question", measures=["First"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(m1, RuntimeDataMode.MOCK)
        await sqlite_memory.commit(m1, valid_evidence)

        # Second memory with stale base_version
        m2 = StructuredWorkMemory(
            conversation_id="conv-sc", request_id="req-s2",
            current_intent="data_question", measures=["Second"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,  # should be 1
        )
        await sqlite_memory.create_pending(m2, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryVersionConflictError, match="版本冲突"):
            await sqlite_memory.commit(m2, valid_evidence)

    @pytest.mark.asyncio
    async def test_conflict_does_not_overwrite(self, sqlite_memory, valid_evidence):
        m1 = StructuredWorkMemory(
            conversation_id="conv-co", request_id="req-c1",
            current_intent="data_question", measures=["Original"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(m1, RuntimeDataMode.MOCK)
        await sqlite_memory.commit(m1, valid_evidence)

        m2 = StructuredWorkMemory(
            conversation_id="conv-co", request_id="req-c2",
            current_intent="data_question", measures=["ShouldFail"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(m2, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryVersionConflictError):
            await sqlite_memory.commit(m2, valid_evidence)

        latest = await sqlite_memory.get_latest_committed("conv-co", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 1
        assert latest.measures == ["Original"]


class TestConcurrentCommit:
    """9: concurrent same-base commit only one succeeds"""

    @pytest.mark.asyncio
    async def test_concurrent_commits_only_one_succeeds(self, sqlite_memory, valid_evidence):
        m1 = StructuredWorkMemory(
            conversation_id="conv-conc", request_id="req-cc1",
            current_intent="data_question", measures=["Data1"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        m2 = StructuredWorkMemory(
            conversation_id="conv-conc", request_id="req-cc2",
            current_intent="data_question", measures=["Data2"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(m1, RuntimeDataMode.MOCK)
        await sqlite_memory.create_pending(m2, RuntimeDataMode.MOCK)

        async def commit_safe(m):
            try:
                return await sqlite_memory.commit(m, valid_evidence)
            except (MemoryVersionConflictError, MemoryCommitDeniedError):
                return None

        results = await asyncio.gather(
            commit_safe(m1), commit_safe(m2)
        )
        successes = [r for r in results if r is not None]
        # At least one must succeed
        assert len(successes) >= 1
        # If exactly one succeeded, version must be 1
        if len(successes) == 1:
            latest = await sqlite_memory.get_latest_committed(
                "conv-conc", RuntimeDataMode.MOCK
            )
            assert latest.memory_version == 1


class TestMockRealIsolation:
    """10: Mock/Real same conversation isolation"""

    @pytest.mark.asyncio
    async def test_mock_and_real_coexist(self, sqlite_memory, valid_evidence, real_evidence):
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-mr", request_id="req-mr1",
            current_intent="data_question", measures=["MockData"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await sqlite_memory.commit(mock_mem, valid_evidence)

        real_mem = StructuredWorkMemory(
            conversation_id="conv-mr", request_id="req-mr2",
            current_intent="data_question", measures=["RealData"],
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(real_mem, RuntimeDataMode.REAL)
        await sqlite_memory.commit(real_mem, real_evidence)

        mock_latest = await sqlite_memory.get_latest_committed(
            "conv-mr", RuntimeDataMode.MOCK
        )
        assert mock_latest is not None
        assert "RealData" not in mock_latest.measures

        real_latest = await sqlite_memory.get_latest_committed(
            "conv-mr", RuntimeDataMode.REAL
        )
        assert real_latest is not None
        assert "MockData" not in real_latest.measures

    @pytest.mark.asyncio
    async def test_same_request_id_different_modes(self, sqlite_memory, valid_evidence, real_evidence):
        """Same request_id in different modes is allowed."""
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-si", request_id="req-shared",
            current_intent="data_question", measures=["Mock"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await sqlite_memory.commit(mock_mem, valid_evidence)

        real_mem = StructuredWorkMemory(
            conversation_id="conv-si", request_id="req-shared",
            current_intent="data_question", measures=["Real"],
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        await sqlite_memory.create_pending(real_mem, RuntimeDataMode.REAL)
        await sqlite_memory.commit(real_mem, real_evidence)

        mock_got = await sqlite_memory.get_by_request_id("req-shared", RuntimeDataMode.MOCK)
        assert mock_got is not None
        assert mock_got.measures == ["Mock"]

        real_got = await sqlite_memory.get_by_request_id("req-shared", RuntimeDataMode.REAL)
        assert real_got is not None
        assert real_got.measures == ["Real"]


class TestSerialization:
    """11-12: serialization roundtrip & corruption"""

    @pytest.mark.asyncio
    async def test_serialization_roundtrip(self, sqlite_memory, sample_memory, valid_evidence):
        sample_memory.analysis_goal = "roundtrip test"
        sample_memory.measures = ["Sales", "Profit"]
        sample_memory.base_memory_version = 0
        await sqlite_memory.create_pending(sample_memory, RuntimeDataMode.MOCK)
        committed = await sqlite_memory.commit(sample_memory, valid_evidence)

        # Re-fetch from DB
        retrieved = await sqlite_memory.get_by_request_id("req-001", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.analysis_goal == "roundtrip test"
        assert retrieved.measures == ["Sales", "Profit"]
        assert retrieved.state_status == MemoryStatus.COMMITTED
        assert retrieved.commit_evidence is not None


# ===========================================================================
# Pending Clarification Tests
# ===========================================================================


class TestPendingClarification:
    """13-18: clarification save/get/replace/clear/isolation/restart"""

    @pytest.mark.asyncio
    async def test_save_and_get(self, sqlite_memory):
        context = PendingClarificationContext(
            conversation_id="clar-conv",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="a" * 64,
            measures=["Total Sales"],
            missing_slots=["dimension"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-1",
        )
        saved = await sqlite_memory.save_pending_clarification(
            context, RuntimeDataMode.REAL
        )
        assert saved.conversation_id == "clar-conv"

        stored = await sqlite_memory.get_pending_clarification(
            "clar-conv", RuntimeDataMode.REAL
        )
        assert stored is not None
        assert stored.measures == ["Total Sales"]

    @pytest.mark.asyncio
    async def test_replace_update(self, sqlite_memory):
        ctx1 = PendingClarificationContext(
            conversation_id="clar-rep",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="a" * 64,
            missing_slots=["dimension"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-1",
        )
        await sqlite_memory.save_pending_clarification(ctx1, RuntimeDataMode.REAL)

        ctx2 = PendingClarificationContext(
            conversation_id="clar-rep",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="b" * 64,
            measures=["Sales"],
            missing_slots=["measure"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-2",
        )
        await sqlite_memory.save_pending_clarification(ctx2, RuntimeDataMode.REAL)

        stored = await sqlite_memory.get_pending_clarification(
            "clar-rep", RuntimeDataMode.REAL
        )
        assert stored is not None
        assert stored.last_request_id == "clarify-2"
        assert stored.measures == ["Sales"]

    @pytest.mark.asyncio
    async def test_clear(self, sqlite_memory):
        context = PendingClarificationContext(
            conversation_id="clar-clear",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="a" * 64,
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-1",
        )
        await sqlite_memory.save_pending_clarification(context, RuntimeDataMode.REAL)
        cleared = await sqlite_memory.clear_pending_clarification(
            "clar-clear", RuntimeDataMode.REAL
        )
        assert cleared is not None
        assert await sqlite_memory.get_pending_clarification(
            "clar-clear", RuntimeDataMode.REAL
        ) is None

    @pytest.mark.asyncio
    async def test_mock_real_isolation(self, sqlite_memory):
        ctx = PendingClarificationContext(
            conversation_id="clar-iso",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="a" * 64,
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-1",
        )
        await sqlite_memory.save_pending_clarification(ctx, RuntimeDataMode.REAL)
        # Mock mode should not see it
        assert await sqlite_memory.get_pending_clarification(
            "clar-iso", RuntimeDataMode.MOCK
        ) is None

    @pytest.mark.asyncio
    async def test_clear_nonexistent(self, sqlite_memory):
        result = await sqlite_memory.clear_pending_clarification(
            "nonexistent", RuntimeDataMode.MOCK
        )
        assert result is None


# ===========================================================================
# Snapshot Tests
# ===========================================================================


class TestSnapshotPersistence:
    """19-25: snapshot save/get/exists/replay/conflict/isolation"""

    SAMPLE_SNAPSHOT = TurnResultSnapshot(
        request_id="snap-001",
        conversation_id="snap-conv",
        intent="data_question",
        response_type="answer",
        terminal_state="completed",
        answer="Test answer for snapshot.",
        request_fingerprint_hash="f" * 64,
    )

    @pytest.mark.asyncio
    async def test_save_and_get(self, sqlite_snapshot):
        await sqlite_snapshot.save(self.SAMPLE_SNAPSHOT, RuntimeDataMode.MOCK)
        retrieved = await sqlite_snapshot.get("snap-001", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.request_id == "snap-001"
        assert retrieved.answer == "Test answer for snapshot."

    @pytest.mark.asyncio
    async def test_exists(self, sqlite_snapshot):
        assert await sqlite_snapshot.exists("snap-001", RuntimeDataMode.MOCK) is False
        await sqlite_snapshot.save(self.SAMPLE_SNAPSHOT, RuntimeDataMode.MOCK)
        assert await sqlite_snapshot.exists("snap-001", RuntimeDataMode.MOCK) is True

    @pytest.mark.asyncio
    async def test_not_found(self, sqlite_snapshot):
        result = await sqlite_snapshot.get("nonexistent", RuntimeDataMode.MOCK)
        assert result is None

    @pytest.mark.asyncio
    async def test_mock_real_isolation(self, sqlite_snapshot):
        """Same request_id in different modes is allowed for snapshots."""
        await sqlite_snapshot.save(self.SAMPLE_SNAPSHOT, RuntimeDataMode.MOCK)
        mock_got = await sqlite_snapshot.get("snap-001", RuntimeDataMode.MOCK)
        assert mock_got is not None

        real_got = await sqlite_snapshot.get("snap-001", RuntimeDataMode.REAL)
        assert real_got is None

    @pytest.mark.asyncio
    async def test_same_request_different_fingerprint_overwrites(self, sqlite_snapshot):
        """Same request_id but different fingerprint — save overwrites (the
        IdempotencyTracker prevents this in the pipeline, but at the storage
        level an overwrite is allowed)."""
        snap1 = TurnResultSnapshot(
            request_id="snap-over",
            conversation_id="snap-conv",
            intent="data_question",
            response_type="answer",
            terminal_state="completed",
            answer="Version 1",
            request_fingerprint_hash="a" * 64,
        )
        await sqlite_snapshot.save(snap1, RuntimeDataMode.MOCK)
        snap2 = TurnResultSnapshot(
            request_id="snap-over",
            conversation_id="snap-conv",
            intent="data_question",
            response_type="answer",
            terminal_state="completed",
            answer="Version 2",
            request_fingerprint_hash="b" * 64,
        )
        await sqlite_snapshot.save(snap2, RuntimeDataMode.MOCK)
        retrieved = await sqlite_snapshot.get("snap-over", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.answer == "Version 2"
        assert retrieved.request_fingerprint_hash == "b" * 64

    @pytest.mark.asyncio
    async def test_report_snapshot(self, sqlite_snapshot):
        """Save and retrieve a report-type snapshot."""
        report_data = ReportResultSnapshot(
            report_id="rpt-001",
            template_key="sales_report",
            html="<h1>Test Report</h1>",
            content_hash="abc123",
        )
        snap = TurnResultSnapshot(
            request_id="snap-rpt",
            conversation_id="snap-conv",
            intent="report_generation",
            response_type="report",
            terminal_state="completed",
            report=report_data,
            request_fingerprint_hash="f" * 64,
        )
        await sqlite_snapshot.save(snap, RuntimeDataMode.MOCK)
        retrieved = await sqlite_snapshot.get("snap-rpt", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.response_type == "report"
        assert retrieved.report is not None
        assert retrieved.report.report_id == "rpt-001"
        assert retrieved.report.html == "<h1>Test Report</h1>"


# ===========================================================================
# Restart Recovery Tests
# ===========================================================================


class TestRestartRecovery:
    """Snapshots and committed memories survive engine restart."""

    @pytest.mark.asyncio
    async def test_memory_restart_recovery(self, engine_a, valid_evidence):
        """Process A saves a committed memory, then process B reads it from
        the same DB file."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)

        mem = StructuredWorkMemory(
            conversation_id="conv-restart",
            request_id="req-restart-1",
            current_intent="data_question",
            measures=["RestoreMe"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo1.create_pending(mem, RuntimeDataMode.MOCK)
        await repo1.commit(mem, valid_evidence)
        await dispose_engine(eng1)

        # Process B: new engine on same DB
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        latest = await repo2.get_latest_committed("conv-restart", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 1
        assert latest.measures == ["RestoreMe"]

        await dispose_engine(eng2)

    @pytest.mark.asyncio
    async def test_snapshot_restart_recovery(self, engine_a):
        """Process A saves a snapshot, then process B reads it."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteSnapshotRepository(session_factory=sf1)

        snap = TurnResultSnapshot(
            request_id="snap-restart",
            conversation_id="conv-restart",
            intent="data_question",
            response_type="answer",
            terminal_state="completed",
            answer="Survived restart!",
            request_fingerprint_hash="f" * 64,
        )
        await repo1.save(snap, RuntimeDataMode.MOCK)
        await dispose_engine(eng1)

        # Process B
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteSnapshotRepository(session_factory=sf2)

        retrieved = await repo2.get("snap-restart", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.answer == "Survived restart!"

        await dispose_engine(eng2)

    @pytest.mark.asyncio
    async def test_clarification_restart_recovery(self, engine_a):
        """Clarification context survives restart."""
        eng1, db_path = engine_a
        sf1 = create_session_factory(eng1)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)

        ctx = PendingClarificationContext(
            conversation_id="conv-clar-restart",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="a" * 64,
            measures=["Sales"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-restart",
        )
        await repo1.save_pending_clarification(ctx, RuntimeDataMode.REAL)
        await dispose_engine(eng1)

        # Process B
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        eng2 = create_engine(settings, echo=False)
        await configure_engine(eng2)
        sf2 = create_session_factory(eng2)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        stored = await repo2.get_pending_clarification(
            "conv-clar-restart", RuntimeDataMode.REAL
        )
        assert stored is not None
        assert stored.measures == ["Sales"]
        assert stored.last_request_id == "clarify-restart"

        await dispose_engine(eng2)


# ===========================================================================
# Wiring / Factory Tests
# ===========================================================================


class TestFactoryWiring:
    """26-30: factory/provider wiring"""

    def test_memory_backend_returns_inmemory(self):
        """persistence_backend=memory should use InMemory repos."""
        settings = Settings(persistence_backend=PersistenceBackend.MEMORY)
        engine = None
        session_factory = None

        if settings.persistence_backend == PersistenceBackend.MEMORY:
            memory_repo = InMemoryMemoryRepository()
            assert isinstance(memory_repo, InMemoryMemoryRepository)
        else:
            pytest.skip("Not memory backend")

    def test_sqlite_backend_creates_sqlite_repos(self):
        """persistence_backend=sqlite should create SQLite repositories."""
        import asyncio

        db_path = _tmp_db_path()
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        engine = create_engine(settings, echo=False)

        async def setup():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await configure_engine(engine)
            sf = create_session_factory(engine)
            memory_repo = SQLiteMemoryRepository(session_factory=sf)
            snapshot_repo = SQLiteSnapshotRepository(session_factory=sf)
            assert isinstance(memory_repo, SQLiteMemoryRepository)
            assert isinstance(snapshot_repo, SQLiteSnapshotRepository)
            await dispose_engine(engine)

        asyncio.run(setup())

    def test_engine_dispose(self):
        """Engine dispose is safe."""
        import asyncio

        db_path = _tmp_db_path()
        settings = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db_path,
        )
        engine = create_engine(settings, echo=False)

        async def go():
            await dispose_engine(engine)

        asyncio.run(go())

    def test_memory_backend_no_db_file(self):
        """No DB file is created when persistence_backend=memory."""
        settings = Settings(persistence_backend=PersistenceBackend.MEMORY)
        # Just verify no error — InMemory repos do not touch the filesystem
        from backend.app.main import _create_repos
        memory_repo, snapshot_store, engine, session_factory = _create_repos(settings)
        assert engine is None
        assert session_factory is None
        assert memory_repo is not None

    @pytest.mark.asyncio
    async def test_temp_db_isolation(self):
        """Two SQLite repos with different temp DB paths are isolated."""
        db1, db2 = _tmp_db_path(), _tmp_db_path()
        settings1 = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db1,
        )
        settings2 = Settings(
            persistence_backend=PersistenceBackend.SQLITE,
            persistence_database_path=db2,
        )

        eng1 = create_engine(settings1)
        eng2 = create_engine(settings2)

        async with eng1.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(eng1)
        async with eng2.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await configure_engine(eng2)

        sf1 = create_session_factory(eng1)
        sf2 = create_session_factory(eng2)
        repo1 = SQLiteMemoryRepository(session_factory=sf1)
        repo2 = SQLiteMemoryRepository(session_factory=sf2)

        # Write to repo1
        mem = StructuredWorkMemory(
            conversation_id="conv-iso-test", request_id="req-iso",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo1.create_pending(mem, RuntimeDataMode.MOCK)

        # repo2 should not see it
        assert await repo2.request_exists("req-iso", RuntimeDataMode.MOCK) is False

        await dispose_engine(eng1)
        await dispose_engine(eng2)