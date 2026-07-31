"""M0.3 InMemoryMemoryRepository 单元测试"""

import pytest

from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
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
        runtime_mode="mock",
        is_mock=True,
        llm_provider="mock",
        powerbi_provider="mock_powerbi",
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
        version_matches=True,
    )


class TestInMemoryRepository:
    """InMemoryMemoryRepository 测试"""

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
    async def test_get_latest_committed(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory)
        await repo.commit(sample_memory, valid_evidence, 1)

        # 第二轮
        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            measures=["Profit"],
            runtime_mode="mock",
            is_mock=True,
            memory_version=2,
        )
        await repo.create_pending(m2)
        await repo.commit(m2, valid_evidence, 2)

        latest = await repo.get_latest_committed("conv-001")
        assert latest is not None
        assert latest.request_id == "req-002"
        assert latest.memory_version == 3  # commit 后递增

    @pytest.mark.asyncio
    async def test_get_latest_committed_empty(self, repo):
        result = await repo.get_latest_committed("conv-empty")
        assert result is None

    @pytest.mark.asyncio
    async def test_commit_success(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory)
        committed = await repo.commit(sample_memory, valid_evidence, 1)
        assert committed.state_status == MemoryStatus.COMMITTED
        assert committed.memory_version == 2

    @pytest.mark.asyncio
    async def test_commit_version_conflict(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory)
        # 期望版本 2，但实际版本是 1
        with pytest.raises(MemoryVersionConflictError):
            await repo.commit(sample_memory, valid_evidence, 2)

    @pytest.mark.asyncio
    async def test_commit_nonexistent_request(self, repo, sample_memory, valid_evidence):
        with pytest.raises(MemoryCommitDeniedError):
            await repo.commit(sample_memory, valid_evidence, 1)

    @pytest.mark.asyncio
    async def test_mark_failed(self, repo, sample_memory):
        await repo.create_pending(sample_memory)
        failed = await repo.mark_failed("req-001")
        assert failed is not None
        assert failed.state_status == MemoryStatus.FAILED

    @pytest.mark.asyncio
    async def test_mark_failed_not_found(self, repo):
        result = await repo.mark_failed("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_conversation(self, repo, sample_memory, valid_evidence):
        await repo.create_pending(sample_memory)
        await repo.commit(sample_memory, valid_evidence, 1)

        # 第二轮 failed
        m2 = StructuredWorkMemory(
            conversation_id="conv-001",
            request_id="req-002",
            current_intent="data_question",
            runtime_mode="mock",
            is_mock=True,
        )
        await repo.create_pending(m2)
        await repo.mark_failed("req-002")

        all_memories = await repo.list_by_conversation("conv-001")
        assert len(all_memories) == 2

        committed_only = await repo.list_by_conversation("conv-001", status="committed")
        assert len(committed_only) == 1

    @pytest.mark.asyncio
    async def test_deep_copy_isolation(self, repo, sample_memory):
        """验证深拷贝防止外部修改内部存储"""
        await repo.create_pending(sample_memory)
        retrieved = await repo.get_by_request_id("req-001")
        retrieved.measures.append("ExternalModification")

        # 再次获取，不应包含外部修改
        re_retrieved = await repo.get_by_request_id("req-001")
        assert "ExternalModification" not in re_retrieved.measures

    @pytest.mark.asyncio
    async def test_no_repeat_commit(self, repo, sample_memory, valid_evidence):
        """已 committed 的记录不应重复提交"""
        await repo.create_pending(sample_memory)
        await repo.commit(sample_memory, valid_evidence, 1)
        # 再次尝试提交（版本已变）
        with pytest.raises(MemoryVersionConflictError):
            await repo.commit(sample_memory, valid_evidence, 1)
