"""M0.3.2 InMemoryMemoryRepository 单元测试 — (runtime_mode, request_id) 复合键"""

import asyncio

import pytest

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


@pytest.fixture
def repo():
    return InMemoryMemoryRepository()


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


def _incomplete_evidence(missing: str) -> MemoryCommitEvidence:
    fields = {
        "intent_valid": True,
        "request_allowed": True,
        "query_plan_valid": True,
        "dax_valid": True,
        "tool_execution_succeeded": True,
        "query_result_valid": True,
        "response_valid": True,
    }
    fields[missing] = False
    return MemoryCommitEvidence(**fields, runtime_mode=RuntimeDataMode.MOCK,
                              failure_reason=f"{missing} is False")


class TestVersionSemantics:
    """版本语义：0→1、1→2、base 检查"""

    @pytest.mark.asyncio
    async def test_first_round_version_0_to_1(self, repo, sample_memory, valid_evidence):
        sample_memory.base_memory_version = 0
        sample_memory.memory_version = 0
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        committed = await repo.commit(sample_memory, valid_evidence)
        assert committed.state_status == MemoryStatus.COMMITTED
        assert committed.memory_version == 1
        assert committed.base_memory_version == 0

    @pytest.mark.asyncio
    async def test_second_round_auto_1_to_2(self, repo, sample_memory, valid_evidence):
        sample_memory.base_memory_version = 0
        sample_memory.request_id = "req-001"
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        round1 = await repo.commit(sample_memory, valid_evidence)
        assert round1.memory_version == 1

        latest = await repo.get_latest_committed("conv-001", RuntimeDataMode.MOCK)
        base_v = 0 if latest is None else latest.memory_version

        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            measures=["Profit"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=base_v,
            memory_version=0,
        )
        await repo.create_pending(m2, RuntimeDataMode.MOCK)
        round2 = await repo.commit(m2, valid_evidence)
        assert round2.memory_version == 2
        assert round2.base_memory_version == 1

    @pytest.mark.asyncio
    async def test_no_manual_version_setting(self, repo, sample_memory, valid_evidence):
        sample_memory.base_memory_version = 0
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        committed = await repo.commit(sample_memory, valid_evidence)
        assert committed.memory_version == 1

    @pytest.mark.asyncio
    async def test_stale_base_version_conflict(self, repo, sample_memory, valid_evidence):
        sample_memory.base_memory_version = 0
        sample_memory.request_id = "req-001"
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        await repo.commit(sample_memory, valid_evidence)

        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
            memory_version=0,
        )
        await repo.create_pending(m2, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryVersionConflictError, match="版本冲突"):
            await repo.commit(m2, valid_evidence)

    @pytest.mark.asyncio
    async def test_conflict_does_not_overwrite(self, repo, sample_memory, valid_evidence):
        sample_memory.base_memory_version = 0
        sample_memory.request_id = "req-001"
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        committed = await repo.commit(sample_memory, valid_evidence)
        assert committed.memory_version == 1

        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            measures=["Hacked"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(m2, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryVersionConflictError):
            await repo.commit(m2, valid_evidence)

        latest = await repo.get_latest_committed("conv-001", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 1
        assert latest.request_id == "req-001"
        assert latest.measures == ["SalesAmount"]


class TestEvidenceValidation:
    """证据验证"""

    @pytest.mark.asyncio
    async def test_incomplete_evidence_rejected_intent(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        evidence = _incomplete_evidence("intent_valid")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_incomplete_evidence_rejected_dax(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        evidence = _incomplete_evidence("dax_valid")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_incomplete_evidence_rejected_tool(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        evidence = _incomplete_evidence("tool_execution_succeeded")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_failure_reason_rejected(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True,
            failure_reason="something went wrong",
        )
        with pytest.raises(MemoryCommitDeniedError, match="失败原因"):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_intent_invalid_rejected(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        evidence = MemoryCommitEvidence(
            intent_valid=False, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True,
        )
        with pytest.raises(MemoryCommitDeniedError, match="意图无效"):
            await repo.commit(sample_memory, evidence)


class TestStateValidation:
    """状态验证"""

    @pytest.mark.asyncio
    async def test_failed_cannot_commit(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        await repo.mark_failed("req-001", RuntimeDataMode.MOCK, reason="test failure", stage="tool_execution")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, valid_evidence)

    @pytest.mark.asyncio
    async def test_committed_cannot_recommit(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        await repo.commit(sample_memory, valid_evidence)
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, valid_evidence)

    @pytest.mark.asyncio
    async def test_nonexistent_request_rejected(self, repo, valid_evidence):
        mem = StructuredWorkMemory(
            conversation_id="conv-x", request_id="no-exist",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK,
        )
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(mem, valid_evidence)


class TestMockRealIsolation:
    """Mock/Real 空间隔离 + 复合键共存"""

    @pytest.mark.asyncio
    async def test_mock_only_reads_mock_committed(self, repo, valid_evidence):
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-iso", request_id="req-mock",
            current_intent="data_question", measures=["MockData"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await repo.commit(mock_mem, valid_evidence)

        real_evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.REAL,
        )
        real_mem = StructuredWorkMemory(
            conversation_id="conv-iso", request_id="req-real",
            current_intent="data_question", measures=["RealData"],
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        await repo.create_pending(real_mem, RuntimeDataMode.REAL)
        await repo.commit(real_mem, real_evidence)

        mock_latest = await repo.get_latest_committed("conv-iso", RuntimeDataMode.MOCK)
        assert mock_latest is not None
        assert mock_latest.runtime_mode == RuntimeDataMode.MOCK
        assert "RealData" not in mock_latest.measures

    @pytest.mark.asyncio
    async def test_real_only_reads_real_committed(self, repo, valid_evidence):
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-iso2", request_id="req-mock2",
            current_intent="data_question", measures=["MockData"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await repo.commit(mock_mem, valid_evidence)

        real_mem = StructuredWorkMemory(
            conversation_id="conv-iso2", request_id="req-real2",
            current_intent="data_question", measures=["RealData"],
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        real_evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.REAL,
        )
        await repo.create_pending(real_mem, RuntimeDataMode.REAL)
        await repo.commit(real_mem, real_evidence)

        real_latest = await repo.get_latest_committed("conv-iso2", RuntimeDataMode.REAL)
        assert real_latest is not None
        assert real_latest.runtime_mode == RuntimeDataMode.REAL
        assert "MockData" not in real_latest.measures

    @pytest.mark.asyncio
    async def test_same_conversation_different_modes_invisible(self, repo, valid_evidence):
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-mixed", request_id="req-m",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await repo.commit(mock_mem, valid_evidence)

        real_latest = await repo.get_latest_committed("conv-mixed", RuntimeDataMode.REAL)
        assert real_latest is None

    @pytest.mark.asyncio
    async def test_list_by_conversation_runtime_mode_filter(self, repo, valid_evidence):
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-filter", request_id="req-f1",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await repo.commit(mock_mem, valid_evidence)

        real_mem = StructuredWorkMemory(
            conversation_id="conv-filter", request_id="req-f2",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        real_ev = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.REAL,
        )
        await repo.create_pending(real_mem, RuntimeDataMode.REAL)
        await repo.commit(real_mem, real_ev)

        mock_only = await repo.list_by_conversation(
            "conv-filter", runtime_mode=RuntimeDataMode.MOCK
        )
        real_only = await repo.list_by_conversation(
            "conv-filter", runtime_mode=RuntimeDataMode.REAL
        )
        assert len(mock_only) == 1
        assert mock_only[0].runtime_mode == RuntimeDataMode.MOCK
        assert len(real_only) == 1
        assert real_only[0].runtime_mode == RuntimeDataMode.REAL

    # ---- M0.3.2 新增：复合键跨模式共存 ----

    @pytest.mark.asyncio
    async def test_same_request_id_different_modes_coexist(self, repo, valid_evidence):
        """相同 request_id 在 Mock 和 Real 模式可以各自存在"""
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-coexist", request_id="req-shared",
            current_intent="data_question", measures=["MockData"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem, RuntimeDataMode.MOCK)
        await repo.commit(mock_mem, valid_evidence)

        real_mem = StructuredWorkMemory(
            conversation_id="conv-coexist", request_id="req-shared",
            current_intent="data_question", measures=["RealData"],
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        real_evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.REAL,
        )
        await repo.create_pending(real_mem, RuntimeDataMode.REAL)
        await repo.commit(real_mem, real_evidence)

        # 两种模式各有一条
        mock_retrieved = await repo.get_by_request_id("req-shared", RuntimeDataMode.MOCK)
        assert mock_retrieved is not None
        assert mock_retrieved.runtime_mode == RuntimeDataMode.MOCK

        real_retrieved = await repo.get_by_request_id("req-shared", RuntimeDataMode.REAL)
        assert real_retrieved is not None
        assert real_retrieved.runtime_mode == RuntimeDataMode.REAL

        mock_latest = await repo.get_latest_committed(
            "conv-coexist", RuntimeDataMode.MOCK
        )
        real_latest = await repo.get_latest_committed(
            "conv-coexist", RuntimeDataMode.REAL
        )
        assert mock_latest is not None
        assert mock_latest.measures == ["MockData"]
        assert real_latest is not None
        assert real_latest.measures == ["RealData"]

        mock_rows = await repo.list_by_conversation(
            "conv-coexist", runtime_mode=RuntimeDataMode.MOCK
        )
        real_rows = await repo.list_by_conversation(
            "conv-coexist", runtime_mode=RuntimeDataMode.REAL
        )
        assert [memory.measures for memory in mock_rows] == [["MockData"]]
        assert [memory.measures for memory in real_rows] == [["RealData"]]

    @pytest.mark.asyncio
    async def test_mock_cannot_see_real_record(self, repo, valid_evidence):
        """Mock 查询看不到 Real 记录"""
        real_mem = StructuredWorkMemory(
            conversation_id="conv-see", request_id="req-real-only",
            current_intent="data_question", measures=["RealOnly"],
            runtime_mode=RuntimeDataMode.REAL, is_mock=False,
            base_memory_version=0,
        )
        real_evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.REAL,
        )
        await repo.create_pending(real_mem, RuntimeDataMode.REAL)
        await repo.commit(real_mem, real_evidence)

        # Mock 查询同 request_id
        mock_found = await repo.get_by_request_id("req-real-only", RuntimeDataMode.MOCK)
        assert mock_found is None

    @pytest.mark.asyncio
    async def test_same_mode_duplicate_still_rejected(self, repo, sample_memory):
        """同模式重复 request_id 仍被幂等拦截"""
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryDuplicateError):
            await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)


class TestFailedRecords:
    """失败记录保留审计"""

    @pytest.mark.asyncio
    async def test_mark_failed_preserves_reason(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        failed = await repo.mark_failed(
            "req-001", RuntimeDataMode.MOCK, reason="timeout occurred", stage="tool_execution"
        )
        assert failed is not None
        assert failed.state_status == MemoryStatus.FAILED
        assert failed.failure_reason == "timeout occurred"
        assert failed.failure_stage == "tool_execution"

    @pytest.mark.asyncio
    async def test_mark_failed_not_found(self, repo):
        result = await repo.mark_failed("nonexistent", RuntimeDataMode.MOCK)
        assert result is None

    @pytest.mark.asyncio
    async def test_failed_record_retained_in_list(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        await repo.mark_failed("req-001", RuntimeDataMode.MOCK, reason="test fail")

        all_memories = await repo.list_by_conversation(
            "conv-001", RuntimeDataMode.MOCK
        )
        assert len(all_memories) == 1
        assert all_memories[0].state_status == MemoryStatus.FAILED

        failed_only = await repo.list_by_conversation(
            "conv-001", RuntimeDataMode.MOCK, status="failed"
        )
        assert len(failed_only) == 1


class TestAtomicityAndConcurrency:
    """原子性和并发"""

    @pytest.mark.asyncio
    async def test_concurrent_commits_only_one_succeeds(self, repo, valid_evidence):
        m1 = StructuredWorkMemory(
            conversation_id="conv-conc", request_id="req-c1",
            current_intent="data_question", measures=["Data1"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        m2 = StructuredWorkMemory(
            conversation_id="conv-conc", request_id="req-c2",
            current_intent="data_question", measures=["Data2"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(m1, RuntimeDataMode.MOCK)
        await repo.create_pending(m2, RuntimeDataMode.MOCK)

        async def commit_mem(m):
            try:
                return await repo.commit(m, valid_evidence)
            except (MemoryVersionConflictError, MemoryCommitDeniedError):
                return None

        results = await asyncio.gather(commit_mem(m1), commit_mem(m2))
        successes = [r for r in results if r is not None]
        assert len(successes) >= 1

        latest = await repo.get_latest_committed("conv-conc", RuntimeDataMode.MOCK)
        if len(successes) == 1:
            assert latest.memory_version == 1

    @pytest.mark.asyncio
    async def test_deep_copy_isolation(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        retrieved = await repo.get_by_request_id("req-001", RuntimeDataMode.MOCK)
        retrieved.measures.append("ExternalModification")

        re_retrieved = await repo.get_by_request_id("req-001", RuntimeDataMode.MOCK)
        assert "ExternalModification" not in re_retrieved.measures


class TestBasicOperations:
    """基础 CRUD 操作"""

    @pytest.mark.asyncio
    async def test_create_pending(self, repo, sample_memory):
        result = await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        assert result.state_status == MemoryStatus.PENDING
        assert result.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_request_id_idempotent(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        with pytest.raises(MemoryDuplicateError):
            await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)

    @pytest.mark.asyncio
    async def test_request_exists(self, repo, sample_memory):
        assert await repo.request_exists("req-001", RuntimeDataMode.MOCK) is False
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        assert await repo.request_exists("req-001", RuntimeDataMode.MOCK) is True

    @pytest.mark.asyncio
    async def test_get_by_request_id(self, repo, sample_memory):
        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        retrieved = await repo.get_by_request_id("req-001", RuntimeDataMode.MOCK)
        assert retrieved is not None
        assert retrieved.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_get_by_request_id_not_found(self, repo):
        result = await repo.get_by_request_id("nonexistent", RuntimeDataMode.MOCK)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_committed_empty(self, repo):
        result = await repo.get_latest_committed("conv-empty", RuntimeDataMode.MOCK)
        assert result is None

    @pytest.mark.asyncio
    async def test_commit_saves_all_analysis_fields(self, repo, sample_memory, valid_evidence):
        sample_memory.measures = ["SalesAmount", "Profit"]
        sample_memory.dimensions = ["Region", "Date"]
        sample_memory.filters = [{"field": "Region", "operator": "eq", "value": "华南"}]
        sample_memory.time_range = "本月"
        sample_memory.sort = "SalesAmount DESC"
        sample_memory.top_n = 10
        sample_memory.comparison_mode = "YoY"
        sample_memory.last_query_plan = {"measures": ["SalesAmount"]}
        sample_memory.last_dax = "EVALUATE SUMMARIZECOLUMNS(...)"
        sample_memory.last_query_result_id = "qr-001"
        sample_memory.last_result_summary = "3 rows"
        sample_memory.last_report_id = "rpt-001"
        sample_memory.analysis_goal = "查询本月销售额"
        sample_memory.base_memory_version = 0

        await repo.create_pending(sample_memory, RuntimeDataMode.MOCK)
        committed = await repo.commit(sample_memory, valid_evidence)

        assert committed.measures == ["SalesAmount", "Profit"]
        assert committed.dimensions == ["Region", "Date"]
        assert committed.filters == [{"field": "Region", "operator": "eq", "value": "华南"}]
        assert committed.time_range == "本月"
        assert committed.sort == "SalesAmount DESC"
        assert committed.top_n == 10
        assert committed.comparison_mode == "YoY"
        assert committed.last_query_plan == {"measures": ["SalesAmount"]}
        assert committed.last_dax == "EVALUATE SUMMARIZECOLUMNS(...)"
        assert committed.last_query_result_id == "qr-001"
        assert committed.last_result_summary == "3 rows"
        assert committed.last_report_id == "rpt-001"
        assert committed.analysis_goal == "查询本月销售额"


class TestNoDirectCommit:
    """禁止绕过 Repository 直接 Commit"""

    def test_memory_has_no_public_commit(self):
        mem = StructuredWorkMemory()
        assert not hasattr(mem, "commit") or callable(getattr(mem, "commit", None)) is False
        assert hasattr(mem, "_bump_version")

    def test_memory_has_no_public_bump_version(self):
        mem = StructuredWorkMemory()
        assert not hasattr(mem, "bump_version")


class TestPendingClarificationRepository:
    @pytest.mark.asyncio
    async def test_pending_context_is_separate_from_committed_memory(self, repo):
        pending = PendingClarificationContext(
            conversation_id="clarification-only",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="a" * 64,
            measures=["Total Sales"],
            missing_slots=["dimension"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-2",
        )
        await repo.save_pending_clarification(pending, RuntimeDataMode.REAL)

        stored = await repo.get_pending_clarification(
            "clarification-only", RuntimeDataMode.REAL
        )
        assert stored == pending
        assert await repo.get_latest_committed(
            "clarification-only", RuntimeDataMode.REAL
        ) is None
        assert not await repo.request_exists("clarify-2", RuntimeDataMode.REAL)

    @pytest.mark.asyncio
    async def test_pending_context_is_mode_isolated_and_clearable(self, repo):
        pending = PendingClarificationContext(
            conversation_id="mode-isolated",
            semantic_model_key="local_desktop_model",
            schema_fingerprint="b" * 64,
            missing_slots=["measure"],
            runtime_mode=RuntimeDataMode.REAL,
            last_request_id="clarify-1",
        )
        await repo.save_pending_clarification(pending, RuntimeDataMode.REAL)
        assert await repo.get_pending_clarification(
            "mode-isolated", RuntimeDataMode.MOCK
        ) is None
        assert await repo.clear_pending_clarification(
            "mode-isolated", RuntimeDataMode.REAL
        )
        assert await repo.get_pending_clarification(
            "mode-isolated", RuntimeDataMode.REAL
        ) is None
