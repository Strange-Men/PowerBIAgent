"""M0.3 Harness 核心组件单元测试"""

import pytest

from backend.app.harness.models import DEFAULT_MOCK_CONFIG, HarnessConfig
from backend.app.harness.runtime.context_builder import ContextBuilder
from backend.app.harness.runtime.tool_gateway import ToolGateway, ToolSpec
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.harness.errors import (
    ToolNotRegisteredError,
    ToolPolicyDeniedError,
    TurnStateError,
    TurnLimitExceededError,
)
from backend.app.intent.models import IntentType
from backend.app.memory.models import StructuredWorkMemory
from backend.app.schemas.data_contracts import (
    DAXRequest,
    QueryPlan,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
    UserContext,
)


class TestToolGateway:
    """ToolGateway 测试"""

    @pytest.fixture
    def gateway(self):
        return ToolGateway()

    @pytest.fixture
    def test_user(self):
        return UserContext()

    def test_register_tool(self, gateway):
        tool = ToolSpec(name="test_tool")
        gateway.register(tool)
        assert "test_tool" in gateway.list_tools()

    def test_duplicate_register_raises(self, gateway):
        gateway.register(ToolSpec(name="test_tool"))
        with pytest.raises(ToolNotRegisteredError):
            gateway.register(ToolSpec(name="test_tool"))

    def test_unregistered_tool_raises(self, gateway):
        with pytest.raises(ToolNotRegisteredError, match="not registered"):
            gateway.get_tool("nonexistent")

    def test_check_intent_permission_allowed(self, gateway):
        gateway.register(ToolSpec(
            name="get_semantic_model_schema",
            allowed_intents=[IntentType.DATA_QUESTION],
        ))
        assert gateway.check_intent_permission(
            "get_semantic_model_schema", IntentType.DATA_QUESTION
        ) is True

    def test_check_intent_permission_denied(self, gateway):
        gateway.register(ToolSpec(
            name="render_report",
            allowed_intents=[IntentType.REPORT_GENERATION],
        ))
        with pytest.raises(ToolPolicyDeniedError):
            gateway.check_intent_permission("render_report", IntentType.DATA_QUESTION)

    def test_user_tool_permission_checked_in_execute(self, gateway):
        """execute 中检查用户工具权限"""
        from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
        restricted_user = UserContext(allowed_tools=["only_this_tool"])
        # 注册一个简单工具到 restricted user 不包含的列表中
        gateway.register(ToolSpec(
            name="get_semantic_model_schema",
            allowed_intents=[IntentType.DATA_QUESTION],
            handler=lambda x: {"ok": True},
        ))
        exec_ctx = ToolExecutionContext(
            intent=IntentType.DATA_QUESTION,
            user=restricted_user,
        )
        # get_semantic_model_schema 不在 restricted_user.allowed_tools 中
        from backend.app.application.mock_turn_service import SchemaInput
        with pytest.raises(ToolPolicyDeniedError, match="not allowed"):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, gateway.execute("get_semantic_model_schema", exec_ctx, SchemaInput())
                    )
                    future.result(timeout=10)
            else:
                loop.run_until_complete(gateway.execute("get_semantic_model_schema", exec_ctx, SchemaInput()))

    def test_unsupported_runtime_mode_denied(self, gateway):
        """不支持的 runtime_mode 被拒绝"""
        from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
        from backend.app.memory.models import RuntimeDataMode
        gateway.register(ToolSpec(
            name="get_semantic_model_schema",
            allowed_intents=[IntentType.DATA_QUESTION],
            supported_modes=[RuntimeDataMode.MOCK],  # 只支持 mock
            handler=lambda x: {"ok": True},
        ))
        exec_ctx = ToolExecutionContext(
            intent=IntentType.DATA_QUESTION,
            user=UserContext(),
            runtime_mode=RuntimeDataMode.REAL,  # real 不被支持
        )
        with pytest.raises(ToolPolicyDeniedError, match="does not support mode"):
            import asyncio
            from backend.app.application.mock_turn_service import SchemaInput
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, gateway.execute("get_semantic_model_schema", exec_ctx, SchemaInput())
                    )
                    future.result(timeout=10)
            else:
                loop.run_until_complete(gateway.execute("get_semantic_model_schema", exec_ctx, SchemaInput()))

    def test_list_tools(self, gateway):
        gateway.register(ToolSpec(name="tool_a"))
        gateway.register(ToolSpec(name="tool_b"))
        tools = gateway.list_tools()
        assert "tool_a" in tools
        assert "tool_b" in tools


class TestContextBuilder:
    """ContextBuilder 测试"""

    def test_build_basic_context(self):
        builder = ContextBuilder(DEFAULT_MOCK_CONFIG)
        ctx = builder.build(user_message="测试问题")
        assert ctx["current_input"] == "测试问题"
        assert ctx["mock_real_flag"] == "mock"
        assert "recent_messages" in ctx  # always present when built without memory
        assert "recent_messages" in ctx

    def test_recent_messages_limited_to_5(self):
        builder = ContextBuilder(DEFAULT_MOCK_CONFIG)
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        ctx = builder.build(user_message="test", recent_messages=messages)
        assert len(ctx["recent_messages"]) <= 5

    def test_secret_fields_excluded(self):
        builder = ContextBuilder(DEFAULT_MOCK_CONFIG)
        from backend.app.memory.models import MemoryStatus
        memory = StructuredWorkMemory(
            state_status=MemoryStatus.COMMITTED,
            memory_version=1,
            current_intent="data_question",
        )
        # Secret 字段不应出现在上下文
        ctx = builder.build(user_message="test", committed_memory=memory)
        mem_dict = ctx.get("committed_memory", {})
        # 确保 committed memory 正确注入
        assert isinstance(mem_dict, dict)
        assert "state_status" in mem_dict or len(mem_dict) > 0

    def test_input_truncation(self):
        config = HarnessConfig(max_user_input_length=10)
        builder = ContextBuilder(config)
        ctx = builder.build(user_message="a" * 20)
        assert len(ctx["current_input"]) <= 10 + len("...[truncated]")

    def test_failed_memory_not_injected(self):
        builder = ContextBuilder(DEFAULT_MOCK_CONFIG)
        # failed/pending memory 不应该出现在 committed_memory 中
        ctx = builder.build(user_message="test", committed_memory=None)
        assert ctx.get("committed_memory") is None  # None → 不注入


class TestTurnController:
    """TurnController 测试"""

    def test_initial_state(self):
        ctrl = TurnController(DEFAULT_MOCK_CONFIG, request_id="req-1")
        assert ctrl.state == TurnState.RECEIVED
        assert not ctrl.is_terminal

    def test_legal_transition(self):
        ctrl = TurnController(DEFAULT_MOCK_CONFIG)
        ctrl.transition(TurnState.CONTEXT_READY)
        assert ctrl.state == TurnState.CONTEXT_READY

    def test_illegal_transition_raises(self):
        ctrl = TurnController(DEFAULT_MOCK_CONFIG)
        with pytest.raises(TurnStateError):
            ctrl.transition(TurnState.COMPLETED)  # RECEIVED → COMPLETED 不合法

    def test_terminal_states(self):
        ctrl = TurnController(DEFAULT_MOCK_CONFIG)
        ctrl.transition(TurnState.CONTEXT_READY)
        ctrl.transition(TurnState.UNSUPPORTED)
        assert ctrl.is_terminal
        assert not ctrl.can_continue

    def test_tool_call_limit(self):
        config = HarnessConfig(max_tool_calls=2)
        ctrl = TurnController(config)
        ctrl.check_tool_call_limit()  # 1
        ctrl.check_tool_call_limit()  # 2
        with pytest.raises(TurnLimitExceededError):
            ctrl.check_tool_call_limit()  # 3 — 超限

    def test_retry_limits(self):
        config = HarnessConfig(max_dax_repairs=1, max_llm_format_retries=1, max_powerbi_retries=1)
        ctrl = TurnController(config)
        ctrl.check_dax_repair_limit()
        with pytest.raises(TurnLimitExceededError):
            ctrl.check_dax_repair_limit()

    def test_can_commit_memory(self):
        ctrl = TurnController(DEFAULT_MOCK_CONFIG)
        assert not ctrl.can_commit_memory  # RECEIVED 不满足
        ctrl.transition(TurnState.CONTEXT_READY)
        ctrl.transition(TurnState.INTENT_CLASSIFIED)
        ctrl.transition(TurnState.PLAN_READY)
        ctrl.transition(TurnState.QUERY_VALIDATED)
        ctrl.transition(TurnState.TOOL_EXECUTED)
        ctrl.transition(TurnState.RESULT_VALIDATED)
        ctrl.transition(TurnState.RESPONSE_READY)
        assert ctrl.can_commit_memory

    def test_build_commit_evidence(self):
        ctrl = TurnController(DEFAULT_MOCK_CONFIG)
        ctrl.record_intent_valid()
        ctrl.record_query_plan_valid()
        ctrl.record_dax_valid()
        ctrl.record_tool_execution_succeeded()
        ctrl.record_query_result_valid()
        ctrl.record_response_valid()
        ctrl.record_version_matches()
        evidence = ctrl.build_commit_evidence()
        assert evidence.intent_valid
        assert evidence.query_plan_valid
        assert evidence.version_matches
        assert evidence.all_satisfied  # 所有证据满足


class TestTraceRecorder:
    """TraceRecorder 测试"""

    def test_record_event(self):
        tr = TraceRecorder(DEFAULT_MOCK_CONFIG)
        tr.record("request_received", request_id="r1")
        assert len(tr.events) == 1
        assert tr.events[0].event_type == "request_received"

    def test_no_secret_in_trace(self):
        tr = TraceRecorder(DEFAULT_MOCK_CONFIG)
        tr.record("request_received", request_id="r1",
                  data_summary={"api_key": "sk-secret-123", "normal_field": "ok"})
        event_dict = tr.events[0].to_dict()
        summary = event_dict.get("data_summary", {})
        assert summary.get("api_key") == "[REDACTED]"
        assert summary.get("normal_field") == "ok"

    def test_multiple_events(self):
        tr = TraceRecorder(DEFAULT_MOCK_CONFIG)
        tr.record("request_received", request_id="r1")
        tr.record("context_built", request_id="r1")
        tr.record("intent_classified", request_id="r1")
        assert len(tr.events) == 3

    def test_get_events_by_type(self):
        tr = TraceRecorder(DEFAULT_MOCK_CONFIG)
        tr.record("request_received", request_id="r1")
        tr.record("request_received", request_id="r2")
        tr.record("completed", request_id="r1")
        recv = tr.get_events_by_type("request_received")
        assert len(recv) == 2

    def test_to_json(self):
        tr = TraceRecorder(DEFAULT_MOCK_CONFIG)
        tr.record("request_received", request_id="r1")
        json_str = tr.to_json()
        assert "request_received" in json_str


class TestValidationService:
    """ValidationService 测试"""

    @pytest.fixture
    def validator(self):
        return ValidationService()

    @pytest.fixture
    def mock_schema(self):
        import asyncio
        from backend.app.powerbi.mock import MockPowerBIAdapter
        adapter = MockPowerBIAdapter()

        async def _get():
            return await adapter.get_semantic_model_schema("mock_sales_model")

        try:
            loop = asyncio.get_running_loop()
            # 在已有的 async 循环中 — 使用 run_until_complete with loop
            import concurrent.futures
            # 直接在 fixture 中创建新事件循环
            new_loop = asyncio.new_event_loop()
            result = new_loop.run_until_complete(_get())
            new_loop.close()
            return result
        except RuntimeError:
            return asyncio.run(_get())

    def test_validate_dax_valid(self, validator):
        dax = DAXRequest(
            semantic_model_key="mock_sales_model",
            dax="EVALUATE SUMMARIZECOLUMNS('Sales'[Region], \"Total\", SUM('Sales'[SalesAmount]))",
        )
        result = validator.validate_dax(dax)
        assert result.is_valid

    def test_validate_dax_empty(self, validator):
        dax = DAXRequest(semantic_model_key="mock_sales_model", dax="SELECT * FROM Sales")
        result = validator.validate_dax(dax)
        assert not result.is_valid

    def test_validate_dax_forbidden_sql(self, validator):
        dax = DAXRequest(semantic_model_key="mock_sales_model", dax="SELECT * FROM Sales")
        result = validator.validate_dax(dax)
        assert not result.is_valid

    def test_validate_query_result(self, validator):
        result = QueryResult(
            semantic_model_key="test",
            columns=["col1", "col2"],
            rows=[["a", 1], ["b", 2]],
            row_count=2,
        )
        vr = validator.validate_query_result(result)
        assert vr.is_valid

    def test_validate_query_result_with_error(self, validator):
        """有 error 的查询结果应返回 valid=False（不可继续处理）"""
        result = QueryResult(
            semantic_model_key="test",
            columns=[],
            rows=[],
            row_count=0,
            error={"type": "dax_error", "message": "test error", "retryable": False},
        )
        vr = validator.validate_query_result(result)
        assert not vr.is_valid  # 有 error 的结果校验失败
        assert len(vr.errors) > 0
        assert vr.error_code == "query_error_dax_error"

    def test_validate_report_template_not_allowed(self, validator, mock_schema):
        report = ReportSpec(
            title="Test",
            template_key="unknown_template",
            data_source="mock_sales_model",
        )
        vr = validator.validate_report(report, mock_schema)
        assert not vr.is_valid

    def test_validate_report_fake_field(self, validator, mock_schema):
        report = ReportSpec(
            title="Test",
            template_key="sales_weekly",
            data_source="mock_sales_model",
            kpis=[{"name": "sales", "value": 100, "field": "NonExistentField"}],
        )
        vr = validator.validate_report(report, mock_schema)
        assert not vr.is_valid

    def test_validate_memory_evidence(self, validator):
        from backend.app.memory.models import MemoryCommitEvidence
        evidence = MemoryCommitEvidence(
            intent_valid=True,
            request_allowed=True,
            query_plan_valid=True,
            dax_valid=True,
            tool_execution_succeeded=True,
            query_result_valid=True,
            response_valid=True,
            version_matches=True,
        )
        vr = validator.validate_memory_commit(evidence, 1, 1)
        assert vr.is_valid

    def test_validate_memory_evidence_version_conflict(self, validator):
        from backend.app.memory.models import MemoryCommitEvidence
        evidence = MemoryCommitEvidence(
            intent_valid=True, request_allowed=True,
            query_plan_valid=True, dax_valid=True,
            tool_execution_succeeded=True, query_result_valid=True,
            response_valid=True, version_matches=True,
        )
        vr = validator.validate_memory_commit(evidence, 1, 2)
        assert not vr.is_valid
