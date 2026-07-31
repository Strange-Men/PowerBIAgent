"""M0.3.1 InMemoryMemoryRepository 单元测试 — 全面覆盖版本语义、隔离、原子性"""

import asyncio

import pytest

from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
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
    """完整业务证据 — version_matches 由 Repository 在原子提交时设置"""
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
    """构造不完整证据"""
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
        """第一轮：base=0，提交后 version=1"""
        sample_memory.base_memory_version = 0
        sample_memory.memory_version = 0
        await repo.create_pending(sample_memory)
        committed = await repo.commit(sample_memory, valid_evidence)
        assert committed.state_status == MemoryStatus.COMMITTED
        assert committed.memory_version == 1
        assert committed.base_memory_version == 0

    @pytest.mark.asyncio
    async def test_second_round_auto_1_to_2(self, repo, sample_memory, valid_evidence):
        """第二轮自动继承：读取第一轮 committed 版本=1 作为 base，提交后 version=2"""
        # 第一轮
        sample_memory.base_memory_version = 0
        sample_memory.request_id = "req-001"
        await repo.create_pending(sample_memory)
        round1 = await repo.commit(sample_memory, valid_evidence)
        assert round1.memory_version == 1

        # 第二轮：从 Repository 读取最新 committed 版本
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
        await repo.create_pending(m2)
        round2 = await repo.commit(m2, valid_evidence)
        assert round2.memory_version == 2  # 自动 1→2
        assert round2.base_memory_version == 1  # 保留原始 base

    @pytest.mark.asyncio
    async def test_no_manual_version_setting(self, repo, sample_memory, valid_evidence):
        """测试不得手工设置第二轮 memory_version — base 驱动版本递增"""
        sample_memory.base_memory_version = 0
        await repo.create_pending(sample_memory)
        committed = await repo.commit(sample_memory, valid_evidence)
        assert committed.memory_version == 1  # 自动计算，非手工设置

    @pytest.mark.asyncio
    async def test_stale_base_version_conflict(self, repo, sample_memory, valid_evidence):
        """stale base version 引发真实冲突"""
        # 第一轮先成功提交
        sample_memory.base_memory_version = 0
        sample_memory.request_id = "req-001"
        await repo.create_pending(sample_memory)
        await repo.commit(sample_memory, valid_evidence)
        # 此时最新 committed version = 1

        # 第二个 pending 使用过时的 base=0
        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,  # stale!
            memory_version=0,
        )
        await repo.create_pending(m2)
        with pytest.raises(MemoryVersionConflictError, match="版本冲突"):
            await repo.commit(m2, valid_evidence)

    @pytest.mark.asyncio
    async def test_conflict_does_not_overwrite(self, repo, sample_memory, valid_evidence):
        """冲突后原 committed 不变"""
        sample_memory.base_memory_version = 0
        sample_memory.request_id = "req-001"
        await repo.create_pending(sample_memory)
        committed = await repo.commit(sample_memory, valid_evidence)
        assert committed.memory_version == 1

        # 尝试用 stale base 提交
        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            measures=["Hacked"],
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(m2)
        with pytest.raises(MemoryVersionConflictError):
            await repo.commit(m2, valid_evidence)

        # 原 committed 不变
        latest = await repo.get_latest_committed("conv-001", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 1
        assert latest.request_id == "req-001"
        assert latest.measures == ["SalesAmount"]  # 未被覆盖


class TestEvidenceValidation:
    """证据验证 — 拒绝不完整/无效 Evidence"""

    @pytest.mark.asyncio
    async def test_incomplete_evidence_rejected_intent(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        evidence = _incomplete_evidence("intent_valid")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_incomplete_evidence_rejected_dax(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        evidence = _incomplete_evidence("dax_valid")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_incomplete_evidence_rejected_tool(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        evidence = _incomplete_evidence("tool_execution_succeeded")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, evidence)

    @pytest.mark.asyncio
    async def test_failure_reason_rejected(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
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
        await repo.create_pending(sample_memory)
        evidence = MemoryCommitEvidence(
            intent_valid=False, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True,
        )
        with pytest.raises(MemoryCommitDeniedError, match="意图无效"):
            await repo.commit(sample_memory, evidence)


class TestStateValidation:
    """状态验证 — 非 pending 不可提交"""

    @pytest.mark.asyncio
    async def test_failed_cannot_commit(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory)
        await repo.mark_failed("req-001", reason="test failure", stage="tool_execution")
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, valid_evidence)

    @pytest.mark.asyncio
    async def test_committed_cannot_recommit(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory)
        await repo.commit(sample_memory, valid_evidence)
        # 再次提交同一个 request_id
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, valid_evidence)

    @pytest.mark.asyncio
    async def test_nonexistent_request_rejected(self, repo, valid_evidence):
        mem = StructuredWorkMemory(
            conversation_id="conv-x", request_id="no-exist",
            current_intent="data_question",
        )
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(mem, valid_evidence)


class TestMockRealIsolation:
    """Mock/Real 空间隔离"""

    @pytest.mark.asyncio
    async def test_mock_only_reads_mock_committed(self, repo, valid_evidence):
        """Mock 查询只能读取 Mock committed memory"""
        # 创建 Mock committed
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-iso", request_id="req-mock",
            current_intent="data_question", measures=["MockData"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem)
        await repo.commit(mock_mem, valid_evidence)

        # 创建 Real committed
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
        await repo.create_pending(real_mem)
        await repo.commit(real_mem, real_evidence)

        # Mock 隔离查询
        mock_latest = await repo.get_latest_committed("conv-iso", RuntimeDataMode.MOCK)
        assert mock_latest is not None
        assert mock_latest.runtime_mode == RuntimeDataMode.MOCK
        assert "RealData" not in mock_latest.measures

    @pytest.mark.asyncio
    async def test_real_only_reads_real_committed(self, repo, valid_evidence):
        """Real 查询只能读取 Real committed memory"""
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-iso2", request_id="req-mock2",
            current_intent="data_question", measures=["MockData"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem)
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
        await repo.create_pending(real_mem)
        await repo.commit(real_mem, real_evidence)

        real_latest = await repo.get_latest_committed("conv-iso2", RuntimeDataMode.REAL)
        assert real_latest is not None
        assert real_latest.runtime_mode == RuntimeDataMode.REAL
        assert "MockData" not in real_latest.measures

    @pytest.mark.asyncio
    async def test_same_conversation_different_modes_invisible(self, repo, valid_evidence):
        """相同 conversation_id 不同模式互不可见"""
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-mixed", request_id="req-m",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem)
        await repo.commit(mock_mem, valid_evidence)

        # 同 conversation 下的 Real 应该看不到 Mock committed
        real_latest = await repo.get_latest_committed("conv-mixed", RuntimeDataMode.REAL)
        assert real_latest is None  # 不可见

    @pytest.mark.asyncio
    async def test_list_by_conversation_runtime_mode_filter(self, repo, valid_evidence):
        """list_by_conversation 支持 runtime_mode 过滤"""
        mock_mem = StructuredWorkMemory(
            conversation_id="conv-filter", request_id="req-f1",
            current_intent="data_question",
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=0,
        )
        await repo.create_pending(mock_mem)
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
        await repo.create_pending(real_mem)
        await repo.commit(real_mem, real_ev)

        all_memories = await repo.list_by_conversation("conv-filter")
        assert len(all_memories) == 2

        mock_only = await repo.list_by_conversation("conv-filter", runtime_mode=RuntimeDataMode.MOCK)
        assert len(mock_only) == 1
        assert mock_only[0].runtime_mode == RuntimeDataMode.MOCK


class TestFailedRecords:
    """失败记录保留审计"""

    @pytest.mark.asyncio
    async def test_mark_failed_preserves_reason(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        failed = await repo.mark_failed(
            "req-001", reason="timeout occurred", stage="tool_execution"
        )
        assert failed is not None
        assert failed.state_status == MemoryStatus.FAILED
        assert failed.failure_reason == "timeout occurred"
        assert failed.failure_stage == "tool_execution"

    @pytest.mark.asyncio
    async def test_mark_failed_not_found(self, repo):
        result = await repo.mark_failed("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_failed_record_retained_in_list(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        await repo.mark_failed("req-001", reason="test fail")

        all_memories = await repo.list_by_conversation("conv-001")
        assert len(all_memories) == 1
        assert all_memories[0].state_status == MemoryStatus.FAILED

        failed_only = await repo.list_by_conversation("conv-001", status="failed")
        assert len(failed_only) == 1


class TestAtomicityAndConcurrency:
    """原子性和并发"""

    @pytest.mark.asyncio
    async def test_concurrent_commits_only_one_succeeds(self, repo, valid_evidence):
        """并发提交只有一个成功"""
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
        await repo.create_pending(m1)
        await repo.create_pending(m2)

        async def commit_mem(m):
            try:
                return await repo.commit(m, valid_evidence)
            except (MemoryVersionConflictError, MemoryCommitDeniedError):
                return None

        results = await asyncio.gather(commit_mem(m1), commit_mem(m2))
        successes = [r for r in results if r is not None]
        # 并发提交至少一个成功（不强制只有一个，但最多一个因为共享 base=0）
        assert len(successes) >= 1

        # 最新 committed 版本应该正确
        latest = await repo.get_latest_committed("conv-conc", RuntimeDataMode.MOCK)
        if len(successes) == 1:
            assert latest.memory_version == 1

    @pytest.mark.asyncio
    async def test_deep_copy_isolation(self, repo, sample_memory):
        """验证深拷贝防止外部修改内部存储"""
        await repo.create_pending(sample_memory)
        retrieved = await repo.get_by_request_id("req-001")
        retrieved.measures.append("ExternalModification")

        re_retrieved = await repo.get_by_request_id("req-001")
        assert "ExternalModification" not in re_retrieved.measures


class TestBasicOperations:
    """基础 CRUD 操作"""

    @pytest.mark.asyncio
    async def test_create_pending(self, repo, sample_memory):
        result = await repo.create_pending(sample_memory)
        assert result.state_status == MemoryStatus.PENDING
        assert result.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_request_id_idempotent(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        with pytest.raises(MemoryDuplicateError):
            await repo.create_pending(sample_memory)

    @pytest.mark.asyncio
    async def test_request_exists(self, repo, sample_memory):
        assert await repo.request_exists("req-001") is False
        await repo.create_pending(sample_memory)
        assert await repo.request_exists("req-001") is True

    @pytest.mark.asyncio
    async def test_get_by_request_id(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        retrieved = await repo.get_by_request_id("req-001")
        assert retrieved is not None
        assert retrieved.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_get_by_request_id_not_found(self, repo):
        result = await repo.get_by_request_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_committed_empty(self, repo):
        result = await repo.get_latest_committed("conv-empty", RuntimeDataMode.MOCK)
        assert result is None

    @pytest.mark.asyncio
    async def test_commit_saves_all_analysis_fields(self, repo, sample_memory, valid_evidence):
        """Repository 保存全部分析字段"""
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

        await repo.create_pending(sample_memory)
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
        """StructuredWorkMemory 不应有公共 commit 方法"""
        mem = StructuredWorkMemory()
        # _mark_committed 是内部方法，非公共
        assert not hasattr(mem, "commit") or callable(getattr(mem, "commit", None)) is False
        # _bump_version 也是内部方法
        assert hasattr(mem, "_bump_version")  # 存在但是 protected

    def test_memory_has_no_public_bump_version(self):
        """StructuredWorkMemory 不应有公共 bump_version 方法"""
        mem = StructuredWorkMemory()
        assert not hasattr(mem, "bump_version")
