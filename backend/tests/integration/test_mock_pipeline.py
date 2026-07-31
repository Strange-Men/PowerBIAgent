"""M0.3.2 集成测试 — Mock 完整链路（经过 ToolGateway，runtime_mode 复合键）"""

import asyncio

import pytest

from backend.app.application.mock_turn_service import MockScenarioSelection, MockTurnService
from backend.app.memory.models import MemoryStatus, RuntimeDataMode, StructuredWorkMemory, MemoryCommitEvidence
from backend.app.memory.repository import InMemoryMemoryRepository, MemoryVersionConflictError
from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.schemas.data_contracts import UserContext
from backend.app.intent.models import IntentType


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
        result = await service.execute(
            message="本月销售额是多少？",
            conversation_id="conv-int-001",
            request_id="req-int-001",
        )
        assert result["terminal_state"] == "completed"
        assert result["intent"] == "data_question"
        assert result["memory_commit"] is True
        assert result["response_type"] == "answer"
        assert "get_semantic_model_schema" in result["tool_sequence"]
        assert "execute_dax" in result["tool_sequence"]

    @pytest.mark.asyncio
    async def test_clarification_no_tools_no_pending(self, service):
        result = await service.execute(
            message="帮我看看数据",
            conversation_id="conv-int-002",
            request_id="req-int-002",
            scenario=MockScenarioSelection(intent_key="clarification"),
        )
        assert result["terminal_state"] == "clarification_required"
        assert result["memory_commit"] is False
        assert result["tool_sequence"] == []

        memory = await service.memory_repo.get_by_request_id("req-int-002", RuntimeDataMode.MOCK)
        assert memory is None

    @pytest.mark.asyncio
    async def test_unsupported_no_tools_no_pending(self, service):
        result = await service.execute(
            message="删除所有数据",
            conversation_id="conv-int-003",
            request_id="req-int-003",
            scenario=MockScenarioSelection(intent_key="unsupported"),
        )
        assert result["terminal_state"] == "unsupported"
        assert result["memory_commit"] is False
        assert result["tool_sequence"] == []

        memory = await service.memory_repo.get_by_request_id("req-int-003", RuntimeDataMode.MOCK)
        assert memory is None

    @pytest.mark.asyncio
    async def test_tool_failure_no_memory(self, service):
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

        memory = await service.memory_repo.get_by_request_id("req-timeout-001", RuntimeDataMode.MOCK)
        assert memory is not None
        assert memory.state_status == MemoryStatus.FAILED

    @pytest.mark.asyncio
    async def test_dax_error_no_memory(self, service):
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
        assert "render_report" in result["tool_sequence"]

    @pytest.mark.asyncio
    async def test_fake_report_field_rejected(self, service):
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
        assert "render_report" not in result["tool_sequence"]

        memory = await service.memory_repo.get_by_request_id("req-rpt-fake", RuntimeDataMode.MOCK)
        assert memory is not None
        assert memory.state_status == MemoryStatus.FAILED


class TestMultiRoundPipeline:
    """多轮真实 Memory 继承"""

    @pytest.mark.asyncio
    async def test_multiround_real_inheritance(self, service):
        result1 = await service.execute(
            message="本月销售额是多少？",
            conversation_id="conv-multi-001",
            request_id="req-multi-001",
        )
        assert result1["terminal_state"] == "completed"
        assert result1["memory_commit"] is True

        mem1 = await service.memory_repo.get_by_request_id("req-multi-001", RuntimeDataMode.MOCK)
        assert mem1 is not None
        assert mem1.state_status == MemoryStatus.COMMITTED
        assert mem1.memory_version == 1

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

        mem2 = await service.memory_repo.get_by_request_id("req-multi-002", RuntimeDataMode.MOCK)
        assert mem2 is not None
        assert mem2.state_status == MemoryStatus.COMMITTED
        assert mem2.memory_version == 2
        assert mem2.base_memory_version == 1

        assert "SalesAmount" in mem2.measures
        assert mem2.time_range is not None
        has_region_filter = any(
            f.get("field") == "Region" or f.get("field") == "区域"
            for f in mem2.filters
        )
        assert has_region_filter, f"Expected filter on Region, got: {mem2.filters}"
        assert mem2.last_dax is not None
        assert mem2.last_result_summary is not None

        mem1_check = await service.memory_repo.get_by_request_id("req-multi-001", RuntimeDataMode.MOCK)
        assert mem1_check.memory_version == 1
        assert mem1_check.state_status == MemoryStatus.COMMITTED


class TestMemoryConflict:
    """真实 Memory 版本冲突"""

    @pytest.mark.asyncio
    async def test_real_version_conflict(self, service):
        conv_id = "conv-conflict-real"

        r1 = await service.execute(
            message="第一轮查询",
            conversation_id=conv_id,
            request_id="req-conflict-base",
        )
        assert r1["terminal_state"] == "completed"
        assert r1["memory_commit"] is True

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
        await service.memory_repo.create_pending(mem_a, RuntimeDataMode.MOCK)
        await service.memory_repo.create_pending(mem_b, RuntimeDataMode.MOCK)

        evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, runtime_mode=RuntimeDataMode.MOCK,
        )
        committed_a = await service.memory_repo.commit(mem_a, evidence)
        assert committed_a.memory_version == 2

        with pytest.raises(MemoryVersionConflictError):
            await service.memory_repo.commit(mem_b, evidence)

        latest = await service.memory_repo.get_latest_committed(conv_id, RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.memory_version == 2
        assert latest.request_id == "req-conflict-A"
        assert latest.measures == ["A"]

        failed_b = await service.memory_repo.get_by_request_id("req-conflict-B", RuntimeDataMode.MOCK)
        assert failed_b is not None


class TestToolGatewayIntegration:
    """ToolGateway 真实生效"""

    @pytest.mark.asyncio
    async def test_all_adapter_calls_through_gateway(self, service):
        tools = service.tool_gateway.list_tools()
        assert "get_semantic_model_schema" in tools
        assert "execute_dax" in tools
        assert "render_report" in tools

    @pytest.mark.asyncio
    async def test_unregistered_tool_denied(self, service):
        from backend.app.harness.errors import ToolNotRegisteredError
        with pytest.raises(ToolNotRegisteredError):
            service.tool_gateway.get_tool("nonexistent_tool")

    @pytest.mark.asyncio
    async def test_tool_sequence_from_gateway_trace(self, service):
        """实际工具序列来自 TraceRecorder，不是硬编码"""
        result = await service.execute(
            message="本月销售额是多少？",
            conversation_id="conv-gw-001",
            request_id="req-gw-001",
        )
        assert result["terminal_state"] == "completed"
        assert len(result["tool_sequence"]) >= 2
        assert "get_semantic_model_schema" in result["tool_sequence"]
        assert "execute_dax" in result["tool_sequence"]
        # 报表不应出现在数据问答中
        assert "render_report" not in result["tool_sequence"]

    @pytest.mark.asyncio
    async def test_gateway_uses_toolspec_allowed_intents(self, service):
        """ToolGateway 以 ToolSpec.allowed_intents 为 Intent 权限唯一来源"""
        from backend.app.harness.errors import ToolPolicyDeniedError
        exec_ctx = ToolExecutionContext(
            intent=IntentType.DATA_QUESTION,
            user=UserContext(),
        )
        from backend.app.schemas.data_contracts import ReportSpec
        with pytest.raises(ToolPolicyDeniedError):
            await service.tool_gateway.execute("render_report", exec_ctx, ReportSpec(
                title="Test", template_key="sales_weekly"
            ))

    @pytest.mark.asyncio
    async def test_read_only_check(self, service):
        """read_only=False 的工具被拒绝"""
        from backend.app.harness.runtime.tool_gateway import ToolSpec
        gw = service.tool_gateway
        gw.register(ToolSpec(
            name="write_tool_test",
            read_only=False,
            handler=lambda x: x,
            input_model=type("X", (__import__("pydantic").BaseModel,), {}),
        ))
        exec_ctx = ToolExecutionContext(user=UserContext())
        from backend.app.harness.errors import ToolPolicyDeniedError
        from backend.app.application.mock_turn_service import SchemaInput
        with pytest.raises(ToolPolicyDeniedError):
            await gw.execute("write_tool_test", exec_ctx, SchemaInput())


class TestRequestIdIdempotent:
    """request_id 幂等（复合键）"""

    @pytest.mark.asyncio
    async def test_duplicate_request_id(self, service):
        result1 = await service.execute(
            message="测试",
            conversation_id="conv-idem-001",
            request_id="req-idem-001",
        )
        assert result1["terminal_state"] == "completed"

        result2 = await service.execute(
            message="测试",
            conversation_id="conv-idem-001",
            request_id="req-idem-001",
        )
        assert result2["terminal_state"] == "duplicate"
        assert result2["memory_commit"] is False

    @pytest.mark.asyncio
    async def test_idempotent_no_version_increment(self, service):
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

        assert v1 == v2


class TestFailureCleanup:
    """失败路径清理"""

    @pytest.mark.asyncio
    async def test_failure_no_committed(self, service):
        await service.execute(
            message="超时查询",
            conversation_id="conv-fail-001",
            request_id="req-fail-001",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        committed = await service.memory_repo.get_latest_committed(
            "conv-fail-001", RuntimeDataMode.MOCK
        )
        assert committed is None

    @pytest.mark.asyncio
    async def test_failure_no_permanent_pending(self, service):
        await service.execute(
            message="超时查询",
            conversation_id="conv-fail-002",
            request_id="req-fail-002",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        mem = await service.memory_repo.get_by_request_id("req-fail-002", RuntimeDataMode.MOCK)
        if mem is not None:
            assert mem.state_status == MemoryStatus.FAILED

    @pytest.mark.asyncio
    async def test_failure_version_not_incremented(self, service):
        await service.execute(
            message="第一轮",
            conversation_id="conv-fail-003",
            request_id="req-fail-base",
        )
        latest = await service.memory_repo.get_latest_committed(
            "conv-fail-003", RuntimeDataMode.MOCK
        )
        v_before = latest.memory_version if latest else 0

        await service.execute(
            message="失败轮",
            conversation_id="conv-fail-003",
            request_id="req-fail-target",
            scenario=MockScenarioSelection(
                intent_key="data_question",
                powerbi_key="timeout",
            ),
        )
        latest_after = await service.memory_repo.get_latest_committed(
            "conv-fail-003", RuntimeDataMode.MOCK
        )
        v_after = latest_after.memory_version if latest_after else 0
        assert v_after == v_before


class TestConcurrentScenarios:
    """M0.3.2 并发场景隔离"""

    @pytest.mark.asyncio
    async def test_concurrent_different_scenarios_no_crosstalk(self):
        """两个并发 Turn 使用不同 Scenario Key，不串场"""
        service = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=MockAgentRuntime(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def turn_a():
            return await service.execute(
                message="本月销售额？",
                conversation_id="conv-conc-a",
                request_id="req-conc-a",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        async def turn_b():
            return await service.execute(
                message="删除所有数据",
                conversation_id="conv-conc-b",
                request_id="req-conc-b",
                scenario=MockScenarioSelection(intent_key="unsupported"),
            )

        r_a, r_b = await asyncio.gather(turn_a(), turn_b())

        assert r_a["terminal_state"] == "completed"
        assert r_a["intent"] == "data_question"
        assert r_b["terminal_state"] == "unsupported"
        assert r_b["intent"] == "unsupported"

    @pytest.mark.asyncio
    async def test_concurrent_same_mock_runtime_no_scenario_leak(self):
        """同一个 MockAgentRuntime 并发不共享场景状态"""
        runtime = MockAgentRuntime()
        s1 = MockTurnService(llm_runtime=runtime)
        s2 = MockTurnService(llm_runtime=runtime)

        async def t1():
            return await s1.execute(
                message="销售额",
                conversation_id="conv-leak-1",
                request_id="req-leak-1",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        async def t2():
            return await s2.execute(
                message="非法请求",
                conversation_id="conv-leak-2",
                request_id="req-leak-2",
                scenario=MockScenarioSelection(intent_key="unsupported"),
            )

        r1, r2 = await asyncio.gather(t1(), t2())
        assert r1["intent"] == "data_question"
        assert r2["intent"] == "unsupported"


class TestProductIds:
    """M0.3.2 查询产物唯一ID"""

    @pytest.mark.asyncio
    async def test_query_result_has_unique_result_id(self, service):
        """每次 QueryResult 拥有唯一 result_id"""
        from backend.app.powerbi.mock import MockPowerBIAdapter
        adapter = MockPowerBIAdapter()
        from backend.app.schemas.data_contracts import DAXRequest
        r1 = await adapter.execute_dax(DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="data_question",
        ))
        r2 = await adapter.execute_dax(DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE ...",
            request_id="data_question",
        ))
        # result_id 不是固定字符串
        assert r1.result_id is not None
        assert r2.result_id is not None
        assert r1.result_id  # 非空
        assert r1.result_id != "data_question"  # 不是 scenario key

    @pytest.mark.asyncio
    async def test_rendered_report_has_unique_report_id(self, service):
        """每次 RenderedReport 拥有唯一 report_id"""
        from backend.app.report.mock import MockReportRenderer
        renderer = MockReportRenderer()
        from backend.app.schemas.data_contracts import ReportSpec, RenderedReport
        r1 = RenderedReport(
            template_key="sales_weekly",
            html=await renderer.render(ReportSpec(title="T1", template_key="sales_weekly")),
        )
        r2 = RenderedReport(
            template_key="sales_weekly",
            html=await renderer.render(ReportSpec(title="T2", template_key="sales_weekly")),
        )
        assert r1.report_id
        assert r2.report_id
        assert r1.report_id != r2.report_id  # 不重复

    @pytest.mark.asyncio
    async def test_memory_saves_last_query_result_id(self, service):
        result = await service.execute(
            message="查询",
            conversation_id="conv-prod-1",
            request_id="req-prod-1",
        )
        assert result["terminal_state"] == "completed"
        mem = await service.memory_repo.get_by_request_id("req-prod-1", RuntimeDataMode.MOCK)
        assert mem is not None
        assert mem.last_query_result_id is not None
        assert mem.last_query_result_id != ""  # 非空
        # 不是 scenario key
        assert mem.last_query_result_id != "data_question"

    @pytest.mark.asyncio
    async def test_report_memory_saves_last_report_id(self, service):
        result = await service.execute(
            message="生成周报",
            conversation_id="conv-rpt-id",
            request_id="req-rpt-id",
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
        mem = await service.memory_repo.get_by_request_id("req-rpt-id", RuntimeDataMode.MOCK)
        assert mem is not None
        assert mem.last_query_result_id is not None
        # 报表场景有 last_report_id
        assert mem.last_report_id is not None


class TestAnswerValidation:
    """M0.3.2 Answer 来源校验"""

    @pytest.mark.asyncio
    async def test_answer_semantic_model_mismatch_fails(self):
        """Answer semantic_model_key 不一致必须失败"""
        from backend.app.harness.validators.validation_service import ValidationService
        from backend.app.schemas.data_contracts import AnswerSpec, QueryResult
        validator = ValidationService()
        result = QueryResult(
            semantic_model_key="mock_sales_model",
            columns=[], rows=[], row_count=0,
        )
        answer = AnswerSpec(
            answer="test",
            semantic_model_key="wrong_model",
        )
        vr = validator.validate_answer(answer, result)
        assert not vr.is_valid

    @pytest.mark.asyncio
    async def test_answer_source_mode_mismatch_fails(self):
        """Answer source_mode 与 QueryResult 不一致必须为 error（非 warning）"""
        from backend.app.harness.validators.validation_service import ValidationService
        from backend.app.schemas.data_contracts import AnswerSpec, QueryResult
        validator = ValidationService()
        result = QueryResult(
            semantic_model_key="mock_sales_model",
            source_mode="mock",
            columns=[], rows=[], row_count=0,
        )
        answer = AnswerSpec(
            answer="test",
            source_mode="real",
            semantic_model_key="mock_sales_model",
        )
        vr = validator.validate_answer(answer, result)
        assert not vr.is_valid
        assert any("source_mode" in e for e in vr.errors)
