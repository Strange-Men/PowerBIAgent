"""M0.2 记忆系统单元测试

测试：
 9. MemoryState 创建
10. memory_version 基本规则
11. failed 状态不可作为 committed
12. 模型切换清理策略
13. request_id 字段与幂等契约
"""

import pytest

from backend.app.memory.models import MemoryStatus, StructuredWorkMemory
from backend.app.memory.policies import MemoryPolicies
from backend.app.memory.repository import MemoryCommitDeniedError


class TestMemoryState:
    """Memory 状态和版本测试"""

    def test_create_default_pending(self):
        memory = StructuredWorkMemory()
        assert memory.state_status == MemoryStatus.PENDING
        assert memory.memory_version == 1
        assert memory.request_id is not None

    def test_commit_transition(self):
        memory = StructuredWorkMemory(current_intent="data_question")
        assert memory.state_status == MemoryStatus.PENDING
        memory.commit()
        assert memory.state_status == MemoryStatus.COMMITTED
        assert memory.memory_version == 2  # commit 会 bump version

    def test_fail_transition(self):
        memory = StructuredWorkMemory()
        memory.fail()
        assert memory.state_status == MemoryStatus.FAILED

    def test_failed_cannot_be_committed(self):
        """failed 状态不可作为 committed 状态"""
        memory = StructuredWorkMemory()
        memory.fail()
        assert memory.state_status == MemoryStatus.FAILED
        with pytest.raises(ValueError, match="failed"):
            memory.commit()

    def test_already_committed_denied(self):
        """已 committed 的 Memory 不可被 deny 提交"""
        memory = StructuredWorkMemory(current_intent="data_question")
        memory.commit()
        with pytest.raises(MemoryCommitDeniedError):
            MemoryPolicies.check_commit_eligibility(memory)

    def test_is_committable(self):
        memory = StructuredWorkMemory(current_intent="data_question")
        assert memory.is_committable() is True

    def test_unsupported_not_committable(self):
        memory = StructuredWorkMemory(current_intent="unsupported")
        assert memory.is_committable() is False

    def test_clarification_pending_not_committable(self):
        memory = StructuredWorkMemory(
            current_intent="data_question",
            clarification_pending=True,
        )
        assert memory.is_committable() is False


class TestMemoryVersion:
    """memory_version 乐观锁规则测试"""

    def test_initial_version_is_one(self):
        memory = StructuredWorkMemory()
        assert memory.memory_version == 1

    def test_bump_increments(self):
        memory = StructuredWorkMemory()
        memory.bump_version()
        assert memory.memory_version == 2
        memory.bump_version()
        assert memory.memory_version == 3

    def test_commit_increments_version(self):
        memory = StructuredWorkMemory(current_intent="data_question")
        v_before = memory.memory_version
        memory.commit()
        assert memory.memory_version == v_before + 1

    def test_version_conflict_detection(self):
        """乐观锁版本冲突检测"""
        # 当前版本 3，期望版本 3 → 无冲突
        assert MemoryPolicies.check_version_conflict(3, 3) is False
        # 当前版本 4，期望版本 3 → 冲突
        assert MemoryPolicies.check_version_conflict(4, 3) is True


class TestRequestId:
    """request_id 幂等契约测试"""

    def test_request_id_exists(self):
        memory = StructuredWorkMemory()
        assert memory.request_id is not None
        assert len(memory.request_id) > 0

    def test_request_id_unique_per_instance(self):
        m1 = StructuredWorkMemory()
        m2 = StructuredWorkMemory()
        assert m1.request_id != m2.request_id

    def test_request_id_idempotent_check(self):
        """相同 request_id 应被幂等检测识别"""
        existing = StructuredWorkMemory(request_id="req-001")
        assert MemoryPolicies.check_request_id_idempotent(existing, "req-001") is True
        assert MemoryPolicies.check_request_id_idempotent(existing, "req-002") is False

    def test_request_id_idempotent_none(self):
        """无已有记录时，幂等检查返回 False"""
        assert MemoryPolicies.check_request_id_idempotent(None, "req-001") is False


class TestModelSwitch:
    """模型切换清理策略测试"""

    def test_on_model_switch_clears_analysis_state(self):
        memory = StructuredWorkMemory(
            semantic_model_key="sales_model_v1",
            current_intent="data_question",
            measures=["销售额"],
            dimensions=["区域"],
            filters=[{"field": "区域", "op": "eq", "value": "华南"}],
            time_range="本月",
            last_dax="EVALUATE ...",
            last_query_result_id="qr-001",
        )
        result = MemoryPolicies.on_model_switch(memory, "sales_model_v2")

        assert result.semantic_model_key == "sales_model_v2"
        assert result.measures == []
        assert result.dimensions == []
        assert result.filters == []
        assert result.time_range is None
        assert result.last_dax is None
        assert result.last_query_result_id is None
        assert result.memory_version == 2  # bump occurred

    def test_on_template_switch_preserves_analysis(self):
        memory = StructuredWorkMemory(
            report_template_key="template_old",
            measures=["销售额"],
            dimensions=["区域"],
            last_report_id="rep-001",
        )
        result = MemoryPolicies.on_template_switch(memory, "template_new")

        assert result.report_template_key == "template_new"
        # 分析条件保留
        assert result.measures == ["销售额"]
        assert result.dimensions == ["区域"]
        # 旧 ReportSpec 清理
        assert result.last_report_id is None
        assert result.memory_version == 2

    def test_on_reset_clears_work_memory(self):
        memory = StructuredWorkMemory(
            current_intent="data_question",
            measures=["销售额"],
            dimensions=["区域"],
            last_dax="EVALUATE ...",
            clarification_pending=True,
            clarification_question="需要确认？",
        )
        result = MemoryPolicies.on_reset(memory)

        assert result.current_intent is None
        assert result.measures == []
        assert result.dimensions == []
        assert result.last_dax is None
        assert result.clarification_pending is False
        assert result.clarification_question is None
        assert result.state_status == MemoryStatus.PENDING
        assert result.memory_version == 2

    def test_on_correction_records_change(self):
        memory = StructuredWorkMemory(
            current_intent="data_question",
            measures=["销售额"],
            memory_version=1,
        )
        result = MemoryPolicies.on_correction(memory, "measures", ["销售额"], ["利润"])

        assert result.measures == ["利润"]
        assert result.memory_version == 2


class TestCommitEligibility:
    """记忆提交准入条件测试"""

    def test_no_intent_denied(self):
        memory = StructuredWorkMemory()
        with pytest.raises(MemoryCommitDeniedError, match="无有效意图"):
            MemoryPolicies.check_commit_eligibility(memory)

    def test_unsupported_denied(self):
        memory = StructuredWorkMemory(current_intent="unsupported")
        with pytest.raises(MemoryCommitDeniedError, match="unsupported"):
            MemoryPolicies.check_commit_eligibility(memory)

    def test_clarification_pending_denied(self):
        memory = StructuredWorkMemory(
            current_intent="data_question",
            clarification_pending=True,
        )
        with pytest.raises(MemoryCommitDeniedError, match="待澄清"):
            MemoryPolicies.check_commit_eligibility(memory)

    def test_failed_denied(self):
        memory = StructuredWorkMemory(current_intent="data_question")
        memory.fail()
        with pytest.raises(MemoryCommitDeniedError, match="failed"):
            MemoryPolicies.check_commit_eligibility(memory)

    def test_mock_denied(self):
        memory = StructuredWorkMemory(
            current_intent="data_question",
            is_mock=True,
        )
        with pytest.raises(MemoryCommitDeniedError, match="Mock"):
            MemoryPolicies.check_commit_eligibility(memory)

    def test_valid_memory_passes(self):
        memory = StructuredWorkMemory(current_intent="data_question")
        # 不应 raise
        MemoryPolicies.check_commit_eligibility(memory)


class TestContextAssembly:
    """Context Assembly 契约测试"""

    def test_allowed_keys_exist(self):
        keys = MemoryPolicies.allowed_context_keys()
        assert "committed_memory" in keys
        assert "recent_messages" in keys
        assert "rolling_summary" in keys
        assert "system_rules" in keys
        assert "current_input" in keys

    def test_no_secret_in_allowed(self):
        keys = MemoryPolicies.allowed_context_keys()
        assert "secret" not in keys
        assert "api_key" not in keys
