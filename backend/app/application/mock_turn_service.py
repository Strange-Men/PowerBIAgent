"""MockTurnService — 确定性应用服务（非 FastAPI 接口）

完整流程：接收请求 → 幂等检查 → 加载记忆 → 构建上下文 → 意图识别 →
如果是 clarification/unsupported → 终止（不创建 pending）
否则 → 创建 pending → Gateway 获取 Schema → 验证 QueryPlan →
Gateway 执行 DAX → 验证结果 → 生成 Answer/Report → Gateway 渲染 →
填充 Memory → Repository 原子提交 → 返回结果

所有工具调用必须经过 ToolGateway。
主链路禁止直接调用 Adapter。
由普通、明确、可测试的 Python 流程控制。
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolNotRegisteredError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import DEFAULT_MOCK_CONFIG, HarnessConfig
from backend.app.harness.runtime.context_builder import ContextBuilder
from backend.app.harness.runtime.tool_gateway import ToolGateway, ToolSpec
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMTask
from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryCommitDeniedError,
    MemoryVersionConflictError,
)
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.report.mock import MockReportRenderer
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    DAXRequest,
    QueryPlan,
    QueryResult,
    RenderedReport,
    ReportSpec,
    SemanticModelSchema,
    UserContext,
)


class MockScenarioSelection(BaseModel):
    """结构化 Mock 场景选择 — 每个阶段使用对应 Key"""
    intent_key: str = "data_question"
    query_plan_key: str = "data_question"
    dax_key: str = "data_question"
    powerbi_key: str = "data_question"
    response_key: str = "data_question"

    model_config = {"frozen": True}  # 不可变，防止并发污染


class SchemaInput(BaseModel):
    """get_semantic_model_schema 工具输入"""
    semantic_model_key: str = "mock_sales_model"


class MockTurnService:
    """Mock 轮次服务

    完整的确定性流程控制，所有工具调用经过 ToolGateway。
    """

    def __init__(
        self,
        memory_repo: Optional[InMemoryMemoryRepository] = None,
        llm_runtime: Optional[MockAgentRuntime] = None,
        powerbi_adapter: Optional[MockPowerBIAdapter] = None,
        report_renderer: Optional[MockReportRenderer] = None,
        config: Optional[HarnessConfig] = None,
    ):
        self.memory_repo = memory_repo or InMemoryMemoryRepository()
        self.llm = llm_runtime or MockAgentRuntime()
        self.powerbi = powerbi_adapter or MockPowerBIAdapter()
        self.report_renderer = report_renderer or MockReportRenderer()
        self.config = config or DEFAULT_MOCK_CONFIG

        self.context_builder = ContextBuilder(self.config)
        self.tool_gateway = self._build_tool_gateway()
        self.validator = ValidationService()
        self._trace: Optional[TraceRecorder] = None

    def _build_tool_gateway(self) -> ToolGateway:
        """构建 ToolGateway 并注册三个工具"""
        gw = ToolGateway()
        user = UserContext()

        # 1. get_semantic_model_schema
        async def _get_schema(input_data: SchemaInput) -> SemanticModelSchema:
            return await self.powerbi.get_semantic_model_schema(input_data.semantic_model_key)

        gw.register(ToolSpec(
            name="get_semantic_model_schema",
            description="获取 Power BI 语义模型结构",
            input_model=SchemaInput,
            output_model=SemanticModelSchema,
            timeout_seconds=30.0,
            max_retries=1,
            read_only=True,
            allowed_intents=[IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
            supported_modes=["mock", "real"],
            handler=_get_schema,
        ))

        # 2. execute_dax
        async def _execute_dax(input_data: DAXRequest) -> QueryResult:
            return await self.powerbi.execute_dax(input_data)

        gw.register(ToolSpec(
            name="execute_dax",
            description="执行 DAX 查询",
            input_model=DAXRequest,
            output_model=QueryResult,
            timeout_seconds=30.0,
            max_retries=1,
            read_only=True,
            allowed_intents=[IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION],
            supported_modes=["mock", "real"],
            handler=_execute_dax,
        ))

        # 3. render_report
        async def _render_report(input_data: ReportSpec) -> RenderedReport:
            html = await self.report_renderer.render(input_data)
            return RenderedReport(
                template_key=input_data.template_key,
                html=html,
                source_mode=input_data.source_mode,
            )

        gw.register(ToolSpec(
            name="render_report",
            description="渲染报表为 HTML",
            input_model=ReportSpec,
            output_model=RenderedReport,
            timeout_seconds=60.0,
            max_retries=0,
            read_only=True,
            allowed_intents=[IntentType.REPORT_GENERATION],
            supported_modes=["mock", "real"],
            handler=_render_report,
        ))

        return gw

    async def execute(
        self,
        message: str,
        conversation_id: str = "test-conv",
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
        scenario: Optional[MockScenarioSelection] = None,
        intent_key: Optional[str] = None,
        powerbi_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 Turn 流程

        Args:
            message: 用户输入
            conversation_id: 会话 ID
            request_id: 幂等请求 ID
            semantic_model_key: 语义模型
            report_template_key: 报表模板
            scenario: 五类 Scenario Key（优先于 intent_key/powerbi_key）
            intent_key: [已弃用] 使用 scenario 代替
            powerbi_key: [已弃用] 使用 scenario 代替
        """
        # 构建 Scenario
        if scenario is None:
            scenario = MockScenarioSelection(
                intent_key=intent_key or "data_question",
                query_plan_key=intent_key or "data_question",
                dax_key=intent_key or "data_question",
                powerbi_key=powerbi_key or intent_key or "data_question",
                response_key=intent_key or "data_question",
            )

        req_id = request_id or str(uuid.uuid4())
        trace = TraceRecorder(self.config)
        self._trace = trace
        user = UserContext()

        trace_id = str(uuid.uuid4())
        trace.record("request_received", trace_id=trace_id, request_id=req_id,
                     conversation_id=conversation_id)

        # 1. 检查 request_id 幂等
        if await self.memory_repo.request_exists(req_id):
            existing = await self.memory_repo.get_by_request_id(req_id)
            trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"terminal_state": "duplicate"})
            return self._build_result(
                existing, req_id, "duplicate", trace_id=trace_id,
                tool_sequence=[],
            )

        # 2. 加载最新 committed memory（按 runtime_mode 隔离）
        committed = await self.memory_repo.get_latest_committed(
            conversation_id, RuntimeDataMode.MOCK
        )

        # 3. 构建上下文
        context = self.context_builder.build(
            user_message=message,
            committed_memory=committed,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
        )
        trace.record("context_built", trace_id=trace_id, request_id=req_id)

        # 4. 意图识别
        self.llm.set_scenario(scenario.intent_key)
        intent_result = await self.llm.run(message, context, IntentSpec)
        intent: IntentSpec = intent_result.structured  # type: ignore[assignment]
        trace.record("intent_classified", trace_id=trace_id, request_id=req_id,
                     data_summary={"intent": intent.intent.value})

        # 5. clarification/unsupported → 直接终止，不创建 pending memory
        if intent.intent == IntentType.CLARIFICATION:
            trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"terminal_state": "clarification_required",
                                      "reason": intent.clarification_question})
            return self._build_result(
                None, req_id, "clarification_required",
                intent=intent.intent.value, trace_id=trace_id,
                tool_sequence=[],
            )

        if intent.intent == IntentType.UNSUPPORTED:
            trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"terminal_state": "unsupported",
                                      "reason": intent.unsupported_reason})
            return self._build_result(
                None, req_id, "unsupported",
                intent=intent.intent.value, trace_id=trace_id,
                tool_sequence=[],
            )

        # 6. 创建 pending memory（有明确意图后才创建）
        base_version = committed.memory_version if committed is not None else 0
        memory = StructuredWorkMemory(
            conversation_id=conversation_id,
            request_id=req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            current_intent=intent.intent.value,
            state_status=MemoryStatus.PENDING,
            runtime_mode=RuntimeDataMode.MOCK,
            is_mock=True,
            llm_provider="mock",
            powerbi_provider="mock_powerbi",
            base_memory_version=base_version,
            memory_version=0,
        )
        await self.memory_repo.create_pending(memory)

        # 7. TurnController
        controller = TurnController(self.config, request_id=req_id)
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()

        # 8. 生成 QueryPlan
        self.llm.set_scenario(scenario.query_plan_key)
        plan_result = await self.llm.run(message, context, QueryPlan)
        query_plan: QueryPlan = plan_result.structured  # type: ignore[assignment]
        trace.record("plan_created", trace_id=trace_id, request_id=req_id)

        # 9. 通过 ToolGateway 获取 Schema
        controller.check_tool_call_limit()
        try:
            schema_input = SchemaInput(semantic_model_key=semantic_model_key)
            schema: SemanticModelSchema = await self.tool_gateway.execute(
                "get_semantic_model_schema",
                IntentType.DATA_QUESTION,
                user,
                schema_input,
            )
            trace.record("tool_call_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"tool": "get_semantic_model_schema",
                                      "model": semantic_model_key})
        except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError) as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.TOOL_FAILED)
            await self.memory_repo.mark_failed(req_id, reason=str(e), stage="schema_fetch")
            trace.record("tool_call_failed", trace_id=trace_id, request_id=req_id,
                        error_type=type(e).__name__)
            return self._build_result(
                memory, req_id, "tool_failed", intent=intent.intent.value,
                error_type="schema_fetch_failed", trace_id=trace_id,
                tool_sequence=[],
            )

        controller.transition(TurnState.PLAN_READY)

        # 10. 验证 QueryPlan
        plan_validation = self.validator.validate_query_plan(query_plan, schema)
        if not plan_validation.is_valid:
            controller.set_failure_reason(str(plan_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.memory_repo.mark_failed(
                req_id, reason=str(plan_validation.errors), stage="query_plan_validation"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                        data_summary={"reason": str(plan_validation.errors)})
            return self._build_result(
                memory, req_id, "validation_failed",
                intent=intent.intent.value, error_type="plan_validation_failed",
                trace_id=trace_id, tool_sequence=["get_semantic_model_schema"],
            )

        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)

        # 11. 生成 DAX
        self.llm.set_scenario(scenario.dax_key)
        dax_result = await self.llm.run(message, context, DAXRequest)
        dax_req: DAXRequest = dax_result.structured  # type: ignore[assignment]
        dax_req.semantic_model_key = semantic_model_key
        dax_req.request_id = scenario.powerbi_key
        dax_req.is_mock = True

        # 验证 DAX
        dax_validation = self.validator.validate_dax(dax_req)
        if not dax_validation.is_valid:
            controller.set_failure_reason(str(dax_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.memory_repo.mark_failed(
                req_id, reason=str(dax_validation.errors), stage="dax_validation"
            )
            return self._build_result(
                memory, req_id, "validation_failed",
                intent=intent.intent.value, error_type="dax_validation_failed",
                trace_id=trace_id, tool_sequence=["get_semantic_model_schema"],
            )

        controller.record_dax_valid()

        # 12. 通过 ToolGateway 执行 DAX
        controller.check_tool_call_limit()
        try:
            query_result: QueryResult = await self.tool_gateway.execute(
                "execute_dax",
                intent.intent,
                user,
                dax_req,
            )
            trace.record("tool_call_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"tool": "execute_dax",
                                      "row_count": query_result.row_count})
        except ToolTimeoutError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.TOOL_FAILED)
            await self.memory_repo.mark_failed(req_id, reason=str(e), stage="dax_execution")
            trace.record("tool_call_failed", trace_id=trace_id, request_id=req_id,
                        error_type="timeout")
            return self._build_result(
                memory, req_id, "tool_failed", intent=intent.intent.value,
                error_type="timeout", trace_id=trace_id,
                tool_sequence=["get_semantic_model_schema"],
            )
        except (ToolExecutionError, ToolPolicyDeniedError) as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.TOOL_FAILED)
            await self.memory_repo.mark_failed(req_id, reason=str(e), stage="dax_execution")
            trace.record("tool_call_failed", trace_id=trace_id, request_id=req_id,
                        error_type=type(e).__name__)
            return self._build_result(
                memory, req_id, "tool_failed", intent=intent.intent.value,
                error_type="tool_execution_failed", trace_id=trace_id,
                tool_sequence=["get_semantic_model_schema"],
            )

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)

        # 13. 验证 QueryResult — error 存在时不可继续
        if query_result.error is not None:
            controller.set_failure_reason(query_result.error.message)
            controller.transition(TurnState.TOOL_FAILED)
            await self.memory_repo.mark_failed(
                req_id, reason=query_result.error.message,
                stage="query_result_error"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                        error_type=query_result.error.type)
            return self._build_result(
                memory, req_id, "tool_failed",
                intent=intent.intent.value, error_type=query_result.error.type,
                trace_id=trace_id,
                tool_sequence=["get_semantic_model_schema", "execute_dax"],
            )

        # 结构一致性验证
        result_validation = self.validator.validate_query_result(query_result)
        if not result_validation.is_valid:
            controller.set_failure_reason(str(result_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.memory_repo.mark_failed(
                req_id, reason=str(result_validation.errors), stage="result_validation"
            )
            return self._build_result(
                memory, req_id, "validation_failed",
                intent=intent.intent.value, error_type="result_validation_failed",
                trace_id=trace_id,
                tool_sequence=["get_semantic_model_schema", "execute_dax"],
            )

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)

        # 14. 生成回答或报表
        tool_sequence = ["get_semantic_model_schema", "execute_dax"]
        if intent.intent == IntentType.DATA_QUESTION:
            self.llm.set_scenario(scenario.response_key)
            answer_result = await self.llm.run(message, context, AnswerSpec)
            response_obj: AnswerSpec = answer_result.structured  # type: ignore[assignment]
            response_type = "answer"

            # 验证 Answer
            answer_validation = self.validator.validate_answer(response_obj, query_result)
            if not answer_validation.is_valid:
                controller.set_failure_reason(str(answer_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.memory_repo.mark_failed(
                    req_id, reason=str(answer_validation.errors), stage="answer_validation"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                            error_type="answer_validation_failed")
                return self._build_result(
                    memory, req_id, "response_failed",
                    intent=intent.intent.value, error_type="answer_validation_failed",
                    trace_id=trace_id, tool_sequence=tool_sequence,
                )
        else:
            self.llm.set_scenario(scenario.response_key)
            report_result = await self.llm.run(message, context, ReportSpec)
            report_spec: ReportSpec = report_result.structured  # type: ignore[assignment]

            # 验证 ReportSpec（绑定当前 QueryResult 字段）
            report_validation = self.validator.validate_report(report_spec, schema, query_result)
            if not report_validation.is_valid:
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.memory_repo.mark_failed(
                    req_id, reason=str(report_validation.errors), stage="report_validation"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                            error_type="report_validation_failed")
                return self._build_result(
                    memory, req_id, "response_failed",
                    intent=intent.intent.value, error_type="report_validation_failed",
                    trace_id=trace_id, tool_sequence=tool_sequence,
                )

            # 通过 ToolGateway 渲染报表
            controller.check_tool_call_limit()
            try:
                rendered: RenderedReport = await self.tool_gateway.execute(
                    "render_report",
                    intent.intent,
                    user,
                    report_spec,
                )
                tool_sequence.append("render_report")
                trace.record("tool_call_completed", trace_id=trace_id, request_id=req_id,
                            data_summary={"tool": "render_report",
                                          "template": report_spec.template_key})
            except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError) as e:
                controller.set_failure_reason(str(e))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.memory_repo.mark_failed(
                    req_id, reason=str(e), stage="report_render"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                            error_type="report_render_failed")
                return self._build_result(
                    memory, req_id, "response_failed",
                    intent=intent.intent.value, error_type="report_render_failed",
                    trace_id=trace_id, tool_sequence=tool_sequence,
                )

            response_obj = report_spec
            response_type = "report"

        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)

        # 15. 提交前填充 Memory 全部分析字段
        memory.current_intent = intent.intent.value
        memory.analysis_goal = f"用户提问: {message}"
        memory.semantic_model_key = semantic_model_key
        memory.report_template_key = report_template_key
        memory.measures = query_plan.measures
        memory.dimensions = query_plan.dimensions
        memory.filters = [f.model_dump() if hasattr(f, "model_dump") else f
                         for f in query_plan.filters]
        memory.time_range = query_plan.time_range
        memory.sort = query_plan.sort
        memory.top_n = query_plan.top_n
        memory.comparison_mode = query_plan.comparison_mode
        memory.last_query_plan = query_plan.model_dump()
        memory.last_dax = dax_req.dax
        memory.last_query_result_id = query_result.request_id or req_id
        memory.last_result_summary = f"{query_result.row_count} rows"
        memory.updated_at = datetime.utcnow()

        # 16. 原子提交
        evidence = controller.build_commit_evidence()
        try:
            committed_memory = await self.memory_repo.commit(memory, evidence)
            controller.record_version_matches()
            controller.transition(TurnState.MEMORY_COMMITTED)
            trace.record("memory_committed", trace_id=trace_id, request_id=req_id,
                        data_summary={"version": committed_memory.memory_version})
        except MemoryVersionConflictError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.MEMORY_CONFLICT)
            await self.memory_repo.mark_failed(
                req_id, reason=str(e), stage="memory_commit"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                        error_type="version_conflict")
            return self._build_result(
                memory, req_id, "memory_conflict", intent=intent.intent.value,
                error_type="version_conflict", trace_id=trace_id,
                tool_sequence=tool_sequence,
            )
        except MemoryCommitDeniedError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.RESPONSE_FAILED)
            await self.memory_repo.mark_failed(
                req_id, reason=str(e), stage="memory_commit"
            )
            return self._build_result(
                memory, req_id, "response_failed", intent=intent.intent.value,
                error_type="memory_commit_denied", trace_id=trace_id,
                tool_sequence=tool_sequence,
            )

        controller.transition(TurnState.COMPLETED)
        trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                    data_summary={"terminal_state": "completed"})

        return self._build_result(
            committed_memory, req_id, "completed",
            intent=intent.intent.value, response_type=response_type,
            trace_id=trace_id, tool_sequence=tool_sequence,
            state_changes={"memory_version": committed_memory.memory_version},
        )

    def _build_result(
        self,
        memory: Optional[StructuredWorkMemory],
        request_id: str,
        terminal_state: str,
        intent: str = "",
        response_type: str = "",
        error_type: Optional[str] = None,
        tool_sequence: Optional[list[str]] = None,
        state_changes: Optional[dict[str, Any]] = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        """构建统一结果字典"""
        if memory is not None:
            return {
                "request_id": request_id,
                "conversation_id": memory.conversation_id,
                "terminal_state": terminal_state,
                "intent": intent or memory.current_intent or "",
                "response_type": response_type,
                "error_type": error_type,
                "tool_sequence": tool_sequence or [],
                "state_changes": state_changes or {},
                "memory_commit": terminal_state == "completed",
                "final_memory_version": memory.memory_version,
                "inherited_context": memory.last_result_summary,
                "allowed_tools": self.tool_gateway.list_tools(),
                "is_mock": True,
                "trace_id": trace_id,
                "measures": memory.measures,
                "dimensions": memory.dimensions,
                "filters": memory.filters,
                "time_range": memory.time_range,
                "last_dax": memory.last_dax,
                "last_result_summary": memory.last_result_summary,
            }
        else:
            return {
                "request_id": request_id,
                "conversation_id": "",
                "terminal_state": terminal_state,
                "intent": intent,
                "response_type": response_type,
                "error_type": error_type,
                "tool_sequence": tool_sequence or [],
                "state_changes": state_changes or {},
                "memory_commit": False,
                "final_memory_version": None,
                "inherited_context": None,
                "allowed_tools": self.tool_gateway.list_tools(),
                "is_mock": True,
                "trace_id": trace_id,
            }
