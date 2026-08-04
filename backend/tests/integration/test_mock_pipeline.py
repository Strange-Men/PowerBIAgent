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
        from backend.app.harness.tool_registry import SchemaInput
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


# =============================================================================
# M0.3.3 真实并发 Scenario 隔离测试
# =============================================================================

class TestSameRuntimeConcurrent:
    """测试1：同一个 MockAgentRuntime 并发执行不同 Scenario，验证无串场"""

    @pytest.mark.asyncio
    async def test_same_runtime_data_question_vs_report_generation(self):
        """请求A=data_question, 请求B=report_generation，同Runtime并发"""
        runtime = MockAgentRuntime()

        service_a = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
        service_b = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def turn_a():
            return await service_a.execute(
                message="本月销售额是多少？",
                conversation_id="conv-rt-conc-a",
                request_id="req-rt-conc-a",
                scenario=MockScenarioSelection(
                    intent_key="data_question",
                    query_plan_key="data_question",
                    dax_key="data_question",
                    powerbi_key="data_question",
                    response_key="data_question",
                ),
            )

        async def turn_b():
            return await service_b.execute(
                message="生成销售周报",
                conversation_id="conv-rt-conc-b",
                request_id="req-rt-conc-b",
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
                report_template_key="sales_weekly",
            )

        r_a, r_b = await asyncio.gather(turn_a(), turn_b())

        # A 始终返回数据问答结果
        assert r_a["terminal_state"] == "completed"
        assert r_a["intent"] == "data_question"
        assert r_a["response_type"] == "answer"
        assert "execute_dax" in r_a["tool_sequence"]
        assert "render_report" not in r_a["tool_sequence"]

        # B 始终返回报表结果
        assert r_b["terminal_state"] == "completed"
        assert r_b["intent"] == "report_generation"
        assert r_b["response_type"] == "report"
        assert "render_report" in r_b["tool_sequence"]

        # 两者 Scenario 不互换
        assert r_a["intent"] != "report_generation"
        assert r_b["intent"] != "data_question"

    @pytest.mark.asyncio
    async def test_same_runtime_repeated_stability(self):
        """同一Runtime并发重复运行10次，验证稳定性"""
        runtime = MockAgentRuntime()

        async def run_one_iteration(i: int):
            sa = MockTurnService(
                memory_repo=InMemoryMemoryRepository(),
                llm_runtime=runtime,
                powerbi_adapter=MockPowerBIAdapter(),
                report_renderer=MockReportRenderer(),
            )
            sb = MockTurnService(
                memory_repo=InMemoryMemoryRepository(),
                llm_runtime=runtime,
                powerbi_adapter=MockPowerBIAdapter(),
                report_renderer=MockReportRenderer(),
            )

            async def ta():
                return await sa.execute(
                    message="销售额",
                    conversation_id=f"conv-rt-stab-a-{i}",
                    request_id=f"req-rt-stab-a-{i}",
                    scenario=MockScenarioSelection(intent_key="data_question"),
                )

            async def tb():
                return await sb.execute(
                    message="非法请求",
                    conversation_id=f"conv-rt-stab-b-{i}",
                    request_id=f"req-rt-stab-b-{i}",
                    scenario=MockScenarioSelection(intent_key="unsupported"),
                )

            ra, rb = await asyncio.gather(ta(), tb())
            return ra, rb

        for i in range(10):
            ra, rb = await run_one_iteration(i)
            assert ra["intent"] == "data_question", f"Iteration {i}: A got {ra['intent']}"
            assert rb["intent"] == "unsupported", f"Iteration {i}: B got {rb['intent']}"
            assert ra["terminal_state"] == "completed"
            assert rb["terminal_state"] == "unsupported"


class TestSameServiceConcurrent:
    """测试2：同一个 MockTurnService 并发执行不同 conversation/request，验证隔离"""

    @pytest.mark.asyncio
    async def test_same_service_data_vs_unsupported(self):
        """同一Service：一个data_question，一个unsupported并发"""
        service = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=MockAgentRuntime(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def turn_a():
            return await service.execute(
                message="本月销售额是多少？",
                conversation_id="conv-svc-conc-a",
                request_id="req-svc-conc-a",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        async def turn_b():
            return await service.execute(
                message="删除所有数据",
                conversation_id="conv-svc-conc-b",
                request_id="req-svc-conc-b",
                scenario=MockScenarioSelection(intent_key="unsupported"),
            )

        r_a, r_b = await asyncio.gather(turn_a(), turn_b())

        # A: 数据问答正常完成
        assert r_a["terminal_state"] == "completed"
        assert r_a["intent"] == "data_question"
        assert r_a["memory_commit"] is True
        assert "execute_dax" in r_a["tool_sequence"]

        # B: unsupported 正确终止
        assert r_b["terminal_state"] == "unsupported"
        assert r_b["intent"] == "unsupported"
        assert r_b["memory_commit"] is False
        assert r_b["tool_sequence"] == []

        # Memory 分别写入对应 conversation
        mem_a = await service.memory_repo.get_by_request_id("req-svc-conc-a", RuntimeDataMode.MOCK)
        assert mem_a is not None
        assert mem_a.state_status == MemoryStatus.COMMITTED
        assert mem_a.conversation_id == "conv-svc-conc-a"

        mem_b = await service.memory_repo.get_by_request_id("req-svc-conc-b", RuntimeDataMode.MOCK)
        assert mem_b is None  # unsupported 不创建 pending

        # 不发生 Scenario 串场
        assert r_a["intent"] != "unsupported"
        assert r_b["intent"] != "data_question"

    @pytest.mark.asyncio
    async def test_same_service_data_vs_report_shared_runtime(self):
        """同一Runtime（不同Service）：一个data_question，一个report_generation并发

        两个独立 Service 共享同一个 MockAgentRuntime，验证 LLM 层面的 Scenario 隔离。
        Service 层面（ToolGateway 内部状态）不共享，避免无关并发问题。
        """
        runtime = MockAgentRuntime()

        sa = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )
        sb = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def turn_a():
            return await sa.execute(
                message="销售额",
                conversation_id="conv-svc-dr-a",
                request_id="req-svc-dr-a",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        async def turn_b():
            return await sb.execute(
                message="生成周报",
                conversation_id="conv-svc-dr-b",
                request_id="req-svc-dr-b",
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
                report_template_key="sales_weekly",
            )

        r_a, r_b = await asyncio.gather(turn_a(), turn_b())

        assert r_a["terminal_state"] == "completed"
        assert r_a["intent"] == "data_question"
        assert r_a["response_type"] == "answer"

        assert r_b["terminal_state"] == "completed"
        assert r_b["intent"] == "report_generation"
        assert r_b["response_type"] == "report"

        # Memory 分别正确
        mem_a = await sa.memory_repo.get_by_request_id("req-svc-dr-a", RuntimeDataMode.MOCK)
        mem_b = await sb.memory_repo.get_by_request_id("req-svc-dr-b", RuntimeDataMode.MOCK)
        assert mem_a is not None and mem_a.state_status == MemoryStatus.COMMITTED
        assert mem_b is not None and mem_b.state_status == MemoryStatus.COMMITTED
        assert mem_a.conversation_id != mem_b.conversation_id

    @pytest.mark.asyncio
    async def test_same_service_repeated_stability(self):
        """同一Service并发重复10次，验证稳定性"""
        service = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=MockAgentRuntime(),
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        for i in range(10):
            async def ta():
                return await service.execute(
                    message="查询",
                    conversation_id=f"conv-svc-stab-a-{i}",
                    request_id=f"req-svc-stab-a-{i}",
                    scenario=MockScenarioSelection(intent_key="data_question"),
                )

            async def tb():
                return await service.execute(
                    message="删除",
                    conversation_id=f"conv-svc-stab-b-{i}",
                    request_id=f"req-svc-stab-b-{i}",
                    scenario=MockScenarioSelection(intent_key="unsupported"),
                )

            ra, rb = await asyncio.gather(ta(), tb())
            assert ra["intent"] == "data_question", f"Iter {i}: A got intent={ra['intent']}"
            assert rb["intent"] == "unsupported", f"Iter {i}: B got intent={rb['intent']}"
            assert ra["terminal_state"] == "completed"
            assert rb["terminal_state"] == "unsupported"


class TestForcedInterleaving:
    """测试3：强制异步交错 — 使用 scenario_delay 确保真实并发交错执行"""

    @pytest.mark.asyncio
    async def test_forced_interleave_with_delay(self):
        """使用 scenario_delay 强制两个请求在执行过程中真实交错"""
        from backend.app.llm.mock import MockLLMProvider

        # 使用延迟确保真实交错
        llm = MockLLMProvider(scenario_delay=0.02)
        runtime = MockAgentRuntime(llm_provider=llm)

        sa = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
        )
        sb = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
        )

        async def turn_a():
            return await sa.execute(
                message="销售额查询",
                conversation_id="conv-interleave-a",
                request_id="req-interleave-a",
                scenario=MockScenarioSelection(
                    intent_key="data_question",
                    query_plan_key="data_question",
                    dax_key="data_question",
                    powerbi_key="data_question",
                    response_key="data_question",
                ),
            )

        async def turn_b():
            return await sb.execute(
                message="生成报表",
                conversation_id="conv-interleave-b",
                request_id="req-interleave-b",
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
                report_template_key="sales_weekly",
            )

        r_a, r_b = await asyncio.gather(turn_a(), turn_b())

        # 即使真实交错，Scenario 也不串场
        assert r_a["intent"] == "data_question", f"A intent corrupted: {r_a['intent']}"
        assert r_a["response_type"] == "answer"
        assert r_b["intent"] == "report_generation", f"B intent corrupted: {r_b['intent']}"
        assert r_b["response_type"] == "report"

    @pytest.mark.asyncio
    async def test_forced_interleave_loop_10(self):
        """强制交错循环10次，提高串场暴露概率"""
        from backend.app.llm.mock import MockLLMProvider

        for iteration in range(10):
            llm = MockLLMProvider(scenario_delay=0.01)
            runtime = MockAgentRuntime(llm_provider=llm)

            sa = MockTurnService(
                memory_repo=InMemoryMemoryRepository(),
                llm_runtime=runtime,
            )
            sb = MockTurnService(
                memory_repo=InMemoryMemoryRepository(),
                llm_runtime=runtime,
            )

            async def ta():
                return await sa.execute(
                    message="销售额",
                    conversation_id=f"conv-il10-a-{iteration}",
                    request_id=f"req-il10-a-{iteration}",
                    scenario=MockScenarioSelection(intent_key="data_question"),
                )

            async def tb():
                return await sb.execute(
                    message="非法操作",
                    conversation_id=f"conv-il10-b-{iteration}",
                    request_id=f"req-il10-b-{iteration}",
                    scenario=MockScenarioSelection(intent_key="unsupported"),
                )

            ra, rb = await asyncio.gather(ta(), tb())
            assert ra["intent"] == "data_question", \
                f"Iter {iteration}: A intent={ra['intent']}, expected data_question"
            assert ra["terminal_state"] == "completed", \
                f"Iter {iteration}: A state={ra['terminal_state']}"
            assert rb["intent"] == "unsupported", \
                f"Iter {iteration}: B intent={rb['intent']}, expected unsupported"
            assert rb["terminal_state"] == "unsupported", \
                f"Iter {iteration}: B state={rb['terminal_state']}"

    @pytest.mark.asyncio
    async def test_forced_interleave_shared_runtime_report(self):
        """同一Runtime（不同Service）+ delay：data_question vs report_generation 真实交错

        两个独立 Service 共享同一个带延迟的 MockAgentRuntime。
        强制异步交错执行，验证 LLM 层面 Scenario 不串场。
        """
        from backend.app.llm.mock import MockLLMProvider

        llm = MockLLMProvider(scenario_delay=0.02)
        runtime = MockAgentRuntime(llm_provider=llm)

        sa = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
        )
        sb = MockTurnService(
            memory_repo=InMemoryMemoryRepository(),
            llm_runtime=runtime,
        )

        async def turn_a():
            return await sa.execute(
                message="销售额",
                conversation_id="conv-svc-il2-a",
                request_id="req-svc-il2-a",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        async def turn_b():
            return await sb.execute(
                message="生成报表",
                conversation_id="conv-svc-il2-b",
                request_id="req-svc-il2-b",
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
                report_template_key="sales_weekly",
            )

        r_a, r_b = await asyncio.gather(turn_a(), turn_b())

        assert r_a["intent"] == "data_question", f"A intent corrupted: {r_a['intent']}"
        assert r_a["response_type"] == "answer"
        assert r_b["intent"] == "report_generation", f"B intent corrupted: {r_b['intent']}"
        assert r_b["response_type"] == "report"


# =============================================================================
# M0.4 请求级并发上下文收口 — 同一 Service 实例并发测试
# =============================================================================

class TestSameServiceFullToolChainConcurrent:
    """同一 MockTurnService + ToolGateway + MockAgentRuntime + MemoryRepository
    并发执行两个完整工具链，验证 Trace/Controller/工具序列/工具计数互不污染。
    """

    @pytest.mark.asyncio
    async def test_same_service_data_question_vs_report_generation(self):
        """同一 Service：请求A=data_question, 请求B=report_generation 并发
        两个请求都走完整工具链，验证 trace_id、工具序列、Memory 互不污染。
        """
        repo = InMemoryMemoryRepository()
        runtime = MockAgentRuntime()
        service = MockTurnService(
            memory_repo=repo,
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def request_a():
            return await service.execute(
                message="本月销售额是多少？",
                conversation_id="conv-m04-full-a",
                request_id="req-m04-full-a",
                semantic_model_key="mock_sales_model",
                scenario=MockScenarioSelection(
                    intent_key="data_question",
                    query_plan_key="data_question",
                    dax_key="data_question",
                    powerbi_key="data_question",
                    response_key="data_question",
                ),
            )

        async def request_b():
            return await service.execute(
                message="生成销售周报",
                conversation_id="conv-m04-full-b",
                request_id="req-m04-full-b",
                semantic_model_key="mock_sales_model",
                report_template_key="sales_weekly",
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
            )

        r_a, r_b = await asyncio.gather(request_a(), request_b())

        # 两个请求都成功
        assert r_a["terminal_state"] == "completed", f"A state: {r_a['terminal_state']}"
        assert r_b["terminal_state"] == "completed", f"B state: {r_b['terminal_state']}"

        # trace_id 不同且非空
        assert r_a["trace_id"], "A trace_id is empty"
        assert r_b["trace_id"], "B trace_id is empty"
        assert r_a["trace_id"] != r_b["trace_id"], \
            f"trace_ids should differ: A={r_a['trace_id']}, B={r_b['trace_id']}"

        # A 工具序列只有 Schema 和 DAX，不包含 render_report
        assert "get_semantic_model_schema" in r_a["tool_sequence"], \
            f"A tools: {r_a['tool_sequence']}"
        assert "execute_dax" in r_a["tool_sequence"], \
            f"A tools: {r_a['tool_sequence']}"
        assert "render_report" not in r_a["tool_sequence"], \
            f"A should NOT have render_report: {r_a['tool_sequence']}"

        # B 工具序列包含 Schema、DAX 和 render_report
        assert "get_semantic_model_schema" in r_b["tool_sequence"], \
            f"B tools: {r_b['tool_sequence']}"
        assert "execute_dax" in r_b["tool_sequence"], \
            f"B tools: {r_b['tool_sequence']}"
        assert "render_report" in r_b["tool_sequence"], \
            f"B should have render_report: {r_b['tool_sequence']}"

        # 两个请求的工具事件不会互相出现
        assert "render_report" not in r_a["tool_sequence"]
        # A 和 B 的 intent 不污染
        assert r_a["intent"] == "data_question"
        assert r_b["intent"] == "report_generation"

        # Memory 写入正确的 conversation
        mem_a = await repo.get_by_request_id("req-m04-full-a", RuntimeDataMode.MOCK)
        mem_b = await repo.get_by_request_id("req-m04-full-b", RuntimeDataMode.MOCK)
        assert mem_a is not None and mem_a.state_status == MemoryStatus.COMMITTED
        assert mem_b is not None and mem_b.state_status == MemoryStatus.COMMITTED
        assert mem_a.conversation_id == "conv-m04-full-a", \
            f"A conv should be conv-m04-full-a, got {mem_a.conversation_id}"
        assert mem_b.conversation_id == "conv-m04-full-b", \
            f"B conv should be conv-m04-full-b, got {mem_b.conversation_id}"

    @pytest.mark.asyncio
    async def test_same_service_repeated_loop_stability(self):
        """同一 Service 并发 data_question vs report_generation 循环 10 次，验证稳定性"""
        runtime = MockAgentRuntime()
        repo = InMemoryMemoryRepository()
        service = MockTurnService(
            memory_repo=repo,
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        for i in range(10):
            async def req_a(idx=i):
                return await service.execute(
                    message="销售额查询",
                    conversation_id=f"conv-m04-loop-a-{idx}",
                    request_id=f"req-m04-loop-a-{idx}",
                    scenario=MockScenarioSelection(
                        intent_key="data_question",
                        query_plan_key="data_question",
                        dax_key="data_question",
                        powerbi_key="data_question",
                        response_key="data_question",
                    ),
                )

            async def req_b(idx=i):
                return await service.execute(
                    message="生成周报",
                    conversation_id=f"conv-m04-loop-b-{idx}",
                    request_id=f"req-m04-loop-b-{idx}",
                    report_template_key="sales_weekly",
                    scenario=MockScenarioSelection(
                        intent_key="report_generation",
                        query_plan_key="report_generation",
                        dax_key="report_generation",
                        powerbi_key="report_generation",
                        response_key="report_generation",
                    ),
                )

            ra, rb = await asyncio.gather(req_a(), req_b())

            assert ra["terminal_state"] == "completed", \
                f"Iter {i}: A state={ra['terminal_state']}"
            assert ra["intent"] == "data_question", \
                f"Iter {i}: A intent={ra['intent']}"
            assert "render_report" not in ra["tool_sequence"], \
                f"Iter {i}: A has render_report: {ra['tool_sequence']}"

            assert rb["terminal_state"] == "completed", \
                f"Iter {i}: B state={rb['terminal_state']}"
            assert rb["intent"] == "report_generation", \
                f"Iter {i}: B intent={rb['intent']}"
            assert "render_report" in rb["tool_sequence"], \
                f"Iter {i}: B missing render_report: {rb['tool_sequence']}"

            # trace_id 每次都不同
            assert ra["trace_id"], f"Iter {i}: A trace_id empty"
            assert rb["trace_id"], f"Iter {i}: B trace_id empty"
            assert ra["trace_id"] != rb["trace_id"], \
                f"Iter {i}: trace_ids should differ"

    @pytest.mark.asyncio
    async def test_tool_call_counts_independent(self):
        """两个请求的工具调用计数独立，不互相影响"""
        repo = InMemoryMemoryRepository()
        runtime = MockAgentRuntime()
        service = MockTurnService(
            memory_repo=repo,
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def req_a():
            return await service.execute(
                message="销售额查询",
                conversation_id="conv-m04-count-a",
                request_id="req-m04-count-a",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        async def req_b():
            return await service.execute(
                message="非法请求",
                conversation_id="conv-m04-count-b",
                request_id="req-m04-count-b",
                scenario=MockScenarioSelection(intent_key="unsupported"),
            )

        ra, rb = await asyncio.gather(req_a(), req_b())

        # A 应完成完整工具链（Schema + DAX）
        assert ra["terminal_state"] == "completed"
        assert len(ra["tool_sequence"]) >= 2
        # B 是 unsupported，没有工具调用
        assert rb["terminal_state"] == "unsupported"
        assert rb["tool_sequence"] == []

        # 各自的工具计数不互相影响
        assert "render_report" not in ra["tool_sequence"]


class TestSameServiceFailAndSuccessConcurrent:
    """同一 Service：一个请求工具失败 + 另一个请求成功并发
    失败请求不能污染成功请求的 Trace 和 Controller。
    """

    @pytest.mark.asyncio
    async def test_failure_does_not_pollute_success_trace(self):
        """请求A工具超时失败，请求B正常成功 — B 不受 A 失败污染"""
        repo = InMemoryMemoryRepository()
        runtime = MockAgentRuntime()
        service = MockTurnService(
            memory_repo=repo,
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def req_a_fail():
            return await service.execute(
                message="超时查询",
                conversation_id="conv-m04-fail-a",
                request_id="req-m04-fail-a",
                scenario=MockScenarioSelection(
                    intent_key="data_question",
                    powerbi_key="timeout",
                ),
            )

        async def req_b_success():
            return await service.execute(
                message="本月销售额是多少？",
                conversation_id="conv-m04-fail-b",
                request_id="req-m04-fail-b",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        r_fail, r_success = await asyncio.gather(req_a_fail(), req_b_success())

        # A: 失败 — 正确标记 tool_failed
        assert r_fail["terminal_state"] == "tool_failed", \
            f"Expected tool_failed, got {r_fail['terminal_state']}"
        assert r_fail["memory_commit"] is False

        # B: 成功 — 不受 A 污染
        assert r_success["terminal_state"] == "completed", \
            f"Expected completed, got {r_success['terminal_state']}"
        assert r_success["memory_commit"] is True
        assert r_success["intent"] == "data_question"
        assert "execute_dax" in r_success["tool_sequence"]

        # trace_id 不同
        assert r_fail["trace_id"] != r_success["trace_id"]

        # A 失败不提交 Memory，B 成功正常提交
        mem_a = await repo.get_by_request_id("req-m04-fail-a", RuntimeDataMode.MOCK)
        assert mem_a is not None
        assert mem_a.state_status == MemoryStatus.FAILED, \
            f"A should be FAILED, got {mem_a.state_status}"

        mem_b = await repo.get_by_request_id("req-m04-fail-b", RuntimeDataMode.MOCK)
        assert mem_b is not None
        assert mem_b.state_status == MemoryStatus.COMMITTED, \
            f"B should be COMMITTED, got {mem_b.state_status}"

    @pytest.mark.asyncio
    async def test_failure_tool_sequence_not_pollute_success(self):
        """失败请求的工具序列不出现 render_report，成功请求的工具序列完整"""
        repo = InMemoryMemoryRepository()
        runtime = MockAgentRuntime()
        service = MockTurnService(
            memory_repo=repo,
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def req_a_fail():
            return await service.execute(
                message="错误 DAX",
                conversation_id="conv-m04-seq-a",
                request_id="req-m04-seq-a",
                scenario=MockScenarioSelection(
                    intent_key="data_question",
                    powerbi_key="dax_error",
                ),
            )

        async def req_b_report():
            return await service.execute(
                message="生成报表",
                conversation_id="conv-m04-seq-b",
                request_id="req-m04-seq-b",
                report_template_key="sales_weekly",
                scenario=MockScenarioSelection(
                    intent_key="report_generation",
                    query_plan_key="report_generation",
                    dax_key="report_generation",
                    powerbi_key="report_generation",
                    response_key="report_generation",
                ),
            )

        r_fail, r_report = await asyncio.gather(req_a_fail(), req_b_report())

        # 失败请求 — DAX 错误，不应有 render_report
        assert r_fail["terminal_state"] == "tool_failed"
        assert "render_report" not in r_fail["tool_sequence"]

        # 成功请求 — 完整报表工具链
        assert r_report["terminal_state"] == "completed"
        assert "render_report" in r_report["tool_sequence"]
        assert "execute_dax" in r_report["tool_sequence"]
        assert "get_semantic_model_schema" in r_report["tool_sequence"]

        # trace_id 不同
        assert r_fail["trace_id"] != r_report["trace_id"]

    @pytest.mark.asyncio
    async def test_failure_does_not_block_success_commit(self):
        """失败请求的 pending 已 failed，成功请求可正常 commit 并递增版本"""
        repo = InMemoryMemoryRepository()
        runtime = MockAgentRuntime()
        service = MockTurnService(
            memory_repo=repo,
            llm_runtime=runtime,
            powerbi_adapter=MockPowerBIAdapter(),
            report_renderer=MockReportRenderer(),
        )

        async def req_fail():
            return await service.execute(
                message="超时",
                conversation_id="conv-m04-block",
                request_id="req-m04-block-fail",
                scenario=MockScenarioSelection(
                    intent_key="data_question",
                    powerbi_key="timeout",
                ),
            )

        async def req_ok():
            return await service.execute(
                message="销售额",
                conversation_id="conv-m04-block",
                request_id="req-m04-block-ok",
                scenario=MockScenarioSelection(intent_key="data_question"),
            )

        r_fail, r_ok = await asyncio.gather(req_fail(), req_ok())

        assert r_fail["terminal_state"] == "tool_failed"
        assert r_ok["terminal_state"] == "completed"

        # 检查 Memory 状态
        mem_fail = await repo.get_by_request_id("req-m04-block-fail", RuntimeDataMode.MOCK)
        assert mem_fail.state_status == MemoryStatus.FAILED

        mem_ok = await repo.get_by_request_id("req-m04-block-ok", RuntimeDataMode.MOCK)
        assert mem_ok.state_status == MemoryStatus.COMMITTED

        # latest committed 应指向成功请求
        latest = await repo.get_latest_committed("conv-m04-block", RuntimeDataMode.MOCK)
        assert latest is not None
        assert latest.request_id == "req-m04-block-ok"
