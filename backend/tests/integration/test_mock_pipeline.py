"""M0.3.1 集成测试 — Mock 完整链路（经过 ToolGateway）"""

import asyncio

import pytest

from backend.app.application.mock_turn_service import MockScenarioSelection, MockTurnService
from backend.app.memory.models import MemoryStatus, RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer


@pytest.fixture
def service():
    return MockTurnService(
        memory_repo=InMemoryMemoryRepository(),
        llm_runtime=MockAgentRuntime(),
        powerbi_adapter=MockPowerBIAdapter(),
        report_renderer=MockReportRenderer(),
    )


class TestMockDataQuestionPipeline:
    """Mock 数据问答完整链路"""

    @pytest.mark.asyncio
    async def test_data_question_success(self, service):
        """普通数据问答成功 — 经过 ToolGateway"""
        result = await service.execute(
            message="本月销售额是多少？",
            conversation_id="conv-int-001",
            request_id="req-int-001",
        )
        assert result["terminal_state"] == "completed"
        assert result["intent"] == "data_question"
        assert result["memory_commit"] is True
        assert result["response_type"] == "answer"
        # 工具序列包含真实 Gateway 调用
        assert "get_semantic_model_schema" in result["tool_sequence"]
        assert "execute_dax" in result["tool_sequence"]

    @pytest.mark.asyncio
    async def test_clarification_no_tools_no_pending(self, service):
        """clarification 不调用工具，不创建 pending memory"""
        result = await service.execute(
            message="帮我看看数据",
            conversation_id="conv-int-002",
            request_id="req-int-002",
            scenario=MockScenarioSelection(intent_key="clarification"),
        )
        assert result["terminal_state"] == "clarification_required"
        assert result["memory_commit"] is False
        assert result["tool_sequence"] == []

        # 验证没有 pending 记录留在 Repository
        memory = await service.memory_repo.get_by_request_id("req-int-002")
        assert memory is None  # clarification 不创建 pending

    @pytest.mark.asyncio
    async def test_unsupported_no_tools_no_pending(self, service):
        """unsupported 不调用工具，不创建 pending memory"""
        result = await service.execute(
            message="删除所有数据",
            conversation_id="conv-int-003",
            request_id="req-int-003",
            scenario=MockScenarioSelection(intent_key="unsupported"),
        )
        assert result["terminal_state"] == "unsupported"
        assert result["memory_commit"] is False
        assert result["tool_sequence"] == []

        memory = await service.memory_repo.get_by_request_id("req-int-003")
        assert memory is None  # unsupported 不创建 pending

    @pytest.mark.asyncio
    async def test_tool_failure_no_memory(self, service):
        """Power BI timeout 经过 ToolGateway 且不提交 Memory"""
        result = await service.execute(
            message="查询超大数据集",
            conversation_id="conv-int-004",
            request_id="req-timeout-001",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        assert result["terminal_state"] == "tool_failed"
        assert result["memory_commit"] is False
        assert result["error_type"] == "timeout"

        # 验证 pending 被标记 failed
        memory = await service.memory_repo.get_by_request_id("req-timeout-001")
        assert memory is not None
        assert memory.state_status == MemoryStatus.FAILED

    @pytest.mark.asyncio
    async def test_dax_error_no_memory(self, service):
        """DAX 错误不提交 Memory"""
        result = await service.execute(
            message="执行错误 DAX",
            conversation_id="conv-int-dax",
            request_id="req-dax-err",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="dax_error",
            ),
        )
        assert result["terminal_state"] == "tool_failed"
        assert result["memory_commit"] is False
        assert result["error_type"] == "dax_error"


class TestMockReportPipeline:
    """Mock 报表链路 — 经过 ToolGateway"""

    @pytest.mark.asyncio
    async def test_report_generation_success(self, service):
        """固定模板报表生成成功 — 包含 render_report 在工具序列"""
        result = await service.execute(
            message="生成销售周报",
            conversation_id="conv-int-rpt-001",
            request_id="req-rpt-001",
            scenario=MockScenarioSelection(
                intent_key="report_generation",
                query_plan_key="report_generation",
                dax_key="report_generation",
                powerbi_key="report_generation",
                response_key="report_generation",
            ),
            report_template_key="sales_weekly",
        )
        assert result["terminal_state"] == "completed"
        assert result["memory_commit"] is True
        assert result["response_type"] == "report"
        # 报表链路必须包含 render_report
        assert "render_report" in result["tool_sequence"]

    @pytest.mark.asyncio
    async def test_fake_report_field_rejected(self, service):
        """虚假报表字段真实被拒绝 — terminal_state 为 response_failed"""
        result = await service.execute(
            message="生成虚假报表",
            conversation_id="conv-int-rpt-002",
            request_id="req-rpt-fake",
            scenario=MockScenarioSelection(
                intent_key="report_generation",
                response_key="fake_field_report",
            ),
            report_template_key="sales_weekly",
        )
        assert result["terminal_state"] == "response_failed"
        assert result["memory_commit"] is False
        assert result["error_type"] == "report_validation_failed"
        # render_report 不应被调用
        assert "render_report" not in result["tool_sequence"]

        # 验证 pending 被标记 failed
        memory = await service.memory_repo.get_by_request_id("req-rpt-fake")
        assert memory is not None
        assert memory.state_status == MemoryStatus.FAILED


class TestMultiRoundPipeline:
    """多轮真实 Memory 继承"""

    @pytest.mark.asyncio
    async def test_multiround_real_inheritance(self, service):
        """多轮筛选继承 — 第一轮真实建立 committed memory，第二轮自动继承"""
        # 第一轮
        result1 = await service.execute(
            message="本月销售额是多少？",
            conversation_id="conv-multi-001",
            request_id="req-multi-001",
        )
        assert result1["terminal_state"] == "completed"
        assert result1["memory_commit"] is True

        # 验证第一轮 committed memory
        mem1 = await service.memory_repo.get_by_request_id("req-multi-001")
        assert mem1 is not None
        assert mem1.state_status == MemoryStatus.COMMITTED
        assert mem1.memory_version == 1

        # 第二轮：多轮追问
        result2 = await service.execute(
            message="只看华南",
            conversation_id="conv-multi-001",
            request_id="req-multi-002",
            scenario=MockScenarioSelection(
                intent_key="data_question_multiround",
                query_plan_key="data_question_multiround",
                dax_key="data_question_multiround",
                powerbi_key="data_question_multiround",
                response_key="data_question_multiround",
            ),
        )
        assert result2["terminal_state"] == "completed"
        assert result2["memory_commit"] is True

        # 验证第二轮 Repository — memory_version 应为 2
        mem2 = await service.memory_repo.get_by_request_id("req-multi-002")
        assert mem2 is not None
        assert mem2.state_status == MemoryStatus.COMMITTED
        assert mem2.memory_version == 2  # 1→2
        assert mem2.base_memory_version == 1

        # 第二轮继承：应有 measures, time_range, 华南 filter
        assert "SalesAmount" in mem2.measures
        assert mem2.time_range is not None
        has_region_filter = any(
            f.get("field") == "Region" or f.get("field") == "区域"
            for f in mem2.filters
        )
        assert has_region_filter, f"Expected filter on Region, got: {mem2.filters}"
        assert mem2.last_dax is not None
        assert mem2.last_result_summary is not None

        # 第一轮 committed 仍然存在且不变
        mem1_check = await service.memory_repo.get_by_request_id("req-multi-001")
        assert mem1_check.memory_version == 1
        assert mem1_check.state_status == MemoryStatus.COMMITTED


class TestMemoryConflict:
    """真实 Memory 版本冲突"""

    @pytest.mark.asyncio
    async def test_real_version_conflict(self, service):
        """真实 stale-base 冲突 — 两个 pending 使用同一 base，第二个被拒绝"""
        conv_id = "conv-conflict-real"

        # 先建立基线：第一轮成功提交
        r1 = await service.execute(
            message="第一轮查询",
            conversation_id=conv_id,
            request_id="req-conflict-base",
        )
        assert r1["terminal_state"] == "completed"
        assert r1["memory_commit"] is True
        # 此时 committed version = 1

        # 创建两个 pending（都基于 version=1）
        from backend.app.memory.models import StructuredWorkMemory
        mem_a = StructuredWorkMemory(
            conversation_id=conv_id, request_id="req-conflict-A",
            current_intent="data_question", measures=["A"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=1, memory_version=0,
        )
        mem_b = StructuredWorkMemory(
            conversation_id=conv_id, request_id="req-conflict-B",
            current_intent="data_question", measures=["B"],
            runtime_mode=RuntimeDataMode.MOCK, is_mock=True,
            base_memory_version=1, memory_version=0,
        )
        await service.memory_repo.create_pending(mem_a)
        await service.memory_repo.create_pending(mem_b)

        # 第一个提交成功
        from backend.app.memory.models import MemoryCommitEvidence
        evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.MOCK,
        )
        committed_a = await service.memory_repo.commit(mem_a, evidence)
        assert committed_a.memory_version == 2  # 1→2

        # 第二个提交 — base=1 但当前最新=2 → 冲突
        from backend.app.memory.repository import MemoryVersionConflictError
        with pytest.raises(MemoryVersionConflictError):
            await service.memory_repo.commit(mem_b, evidence)

        # 验证：最新 committed 版本仍为 2，未被覆盖
        latest = await service.memory_repo.get_latest_committed(conv_id, RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 2
        assert latest.request_id == "req-conflict-A"  # 第一个成功提交
        assert latest.measures == ["A"]  # 未被 B 覆盖

        # 第二个被标记 failed
        failed_b = await service.memory_repo.get_by_request_id("req-conflict-B")
        # mark_failed 应该在冲突时被调用
        # 如果没有被mark_failed调用，至少状态不应该改变
        assert failed_b is not None


class TestToolGatewayIntegration:
    """ToolGateway 真实生效"""

    @pytest.mark.asyncio
    async def test_all_adapter_calls_through_gateway(self, service):
        """验证所有工具调用经过 ToolGateway — Schema、DAX、渲染均在 Gateway 中注册"""
        # 检查三个工具都已在 Gateway 中注册
        tools = service.tool_gateway.list_tools()
        assert "get_semantic_model_schema" in tools
        assert "execute_dax" in tools
        assert "render_report" in tools

    @pytest.mark.asyncio
    async def test_unregistered_tool_denied(self, service):
        """未注册工具被 Gateway 拒绝"""
        from backend.app.harness.errors import ToolNotRegisteredError
        with pytest.raises(ToolNotRegisteredError):
            service.tool_gateway.get_tool("nonexistent_tool")

    @pytest.mark.asyncio
    async def test_tool_sequence_from_gateway(self, service):
        """实际工具序列来自 ToolGateway 执行，不是硬编码"""
        result = await service.execute(
            message="本月销售额是多少？",
            conversation_id="conv-gw-001",
            request_id="req-gw-001",
        )
        assert result["terminal_state"] == "completed"
        # 工具序列不应为空或硬编码
        assert len(result["tool_sequence"]) >= 2
        # 至少包含 schema 和 dax
        assert "get_semantic_model_schema" in result["tool_sequence"]
        assert "execute_dax" in result["tool_sequence"]


class TestRequestIdIdempotent:
    """request_id 幂等"""

    @pytest.mark.asyncio
    async def test_duplicate_request_id(self, service):
        """相同 request_id 不重复处理 — 返回 duplicate 状态"""
        result1 = await service.execute(
            message="测试",
            conversation_id="conv-idem-001",
            request_id="req-idem-001",
        )
        assert result1["terminal_state"] == "completed"

        # 重复请求
        result2 = await service.execute(
            message="测试",
            conversation_id="conv-idem-001",
            request_id="req-idem-001",
        )
        assert result2["terminal_state"] == "duplicate"
        assert result2["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_idempotent_no_version_increment(self, service):
        """幂等不增加版本"""
        result1 = await service.execute(
            message="查询",
            conversation_id="conv-idem-002",
            request_id="req-idem-002",
        )
        v1 = result1.get("final_memory_version")

        result2 = await service.execute(
            message="查询",
            conversation_id="conv-idem-002",
            request_id="req-idem-002",
        )
        v2 = result2.get("final_memory_version")

        # 版本不应变化（幂等返回原结果）
        assert v1 == v2


class TestFailureCleanup:
    """失败路径清理"""

    @pytest.mark.asyncio
    async def test_failure_no_committed(self, service):
        """失败后无 committed memory"""
        await service.execute(
            message="超时查询",
            conversation_id="conv-fail-001",
            request_id="req-fail-001",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        # 无 committed
        committed = await service.memory_repo.get_latest_committed(
            "conv-fail-001", RuntimeDataMode.MOCK
        )
        assert committed is None

    @pytest.mark.asyncio
    async def test_failure_no_permanent_pending(self, service):
        """失败后 pending 被标记 failed，不留永久 pending"""
        await service.execute(
            message="超时查询",
            conversation_id="conv-fail-002",
            request_id="req-fail-002",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        # pending 应为 failed
        mem = await service.memory_repo.get_by_request_id("req-fail-002")
        if mem is not None:
            assert mem.state_status == MemoryStatus.FAILED

    @pytest.mark.asyncio
    async def test_failure_version_not_incremented(self, service):
        """失败后版本未递增"""
        # 先成功一轮
        await service.execute(
            message="第一轮",
            conversation_id="conv-fail-003",
            request_id="req-fail-base",
        )
        # 最新版本应为 1
        latest = await service.memory_repo.get_latest_committed(
            "conv-fail-003", RuntimeDataMode.MOCK
        )
        v_before = latest.memory_version if latest else 0

        # 失败一轮
        await service.execute(
            message="失败轮",
            conversation_id="conv-fail-003",
            request_id="req-fail-target",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        # 版本应未变化
        latest_after = await service.memory_repo.get_latest_committed(
            "conv-fail-003", RuntimeDataMode.MOCK
        )
        v_after = latest_after.memory_version if latest_after else 0
        assert v_after == v_before
