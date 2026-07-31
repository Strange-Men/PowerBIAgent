"""MockTurnService — 确定性应用服务（非 FastAPI 接口）

M0.3.2 修复：
- 工具序列唯一来源：TraceRecorder.get_tool_sequence()，不再手工拼装
- Schema 失败路径合法状态转换
- 统一 _fail_turn 处理所有失败分支
- ToolExecutionContext 传入 Gateway
- Gateway 集成 TraceRecorder
- last_query_result_id/last_report_id 使用唯一 result_id/report_id
- Memory 冲突时 pending 标记 failed、不返回 memory_commit=True
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolNotRegisteredError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import DEFAULT_MOCK_CONFIG, HarnessConfig
from backend.app.harness.runtime.context_builder import ContextBuilder
from backend.app.harness.runtime.tool_gateway import (
    ToolExecutionContext,
    ToolGateway,
    ToolSpec,
)
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
    工具序列唯一来源于 TraceRecorder.get_tool_sequence()。
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
        # M0.4: 删除 self._trace 共享实例字段
        # TraceRecorder 仅存在于 execute() 局部变量中，通过参数显式传递

    def _build_tool_gateway(self) -> ToolGateway:
        """构建 ToolGateway 并注册三个工具"""
        gw = ToolGateway()

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
            supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
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
            supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
            handler=_execute_dax,
        ))

        # 3. render_report
        async def _render_report(input_data: ReportSpec) -> RenderedReport:
            html = await self.report_renderer.render(input_data)
            return RenderedReport(
                report_id=str(uuid.uuid4()),
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
            supported_modes=[RuntimeDataMode.MOCK, RuntimeDataMode.REAL],
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
        """执行完整 Turn 流程"""
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
        trace_id = str(uuid.uuid4())
        trace = TraceRecorder(self.config)
        # M0.4: TraceRecorder 仅作为 execute() 局部变量
        # 不再写入 self._trace，不再注入到 Gateway 共享字段

        user = UserContext()
        runtime_mode = RuntimeDataMode.MOCK if self.config.is_mock else RuntimeDataMode.REAL

        trace.record("request_received", trace_id=trace_id, request_id=req_id,
                     conversation_id=conversation_id)

        # 1. 检查 request_id 幂等
        if await self.memory_repo.request_exists(req_id, runtime_mode):
            existing = await self.memory_repo.get_by_request_id(req_id, runtime_mode)
            trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"terminal_state": "duplicate"})
            return self._build_result(
                existing, req_id, "duplicate", trace_id=trace_id,
                trace=trace,
            )

        # 2. 加载最新 committed memory
        committed = await self.memory_repo.get_latest_committed(
            conversation_id, runtime_mode
        )

        # 3. 构建上下文
        context = self.context_builder.build(
            user_message=message,
            committed_memory=committed,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
        )
        trace.record("context_built", trace_id=trace_id, request_id=req_id)

        # 4. 意图识别 — M0.3.3: scenario_key 通过 context 局部传递，不保存到任何共享状态
        context["mock_scenario_key"] = scenario.intent_key
        intent_result = await self.llm.run(message, context, IntentSpec)
        intent: IntentSpec = intent_result.structured  # type: ignore[assignment]
        trace.record("intent_classified", trace_id=trace_id, request_id=req_id,
                     data_summary={"intent": intent.intent.value})

        # 5. clarification/unsupported → 直接终止，不创建 pending
        if intent.intent == IntentType.CLARIFICATION:
            trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"terminal_state": "clarification_required",
                                      "reason": intent.clarification_question})
            return self._build_result(
                None, req_id, "clarification_required",
                intent=intent.intent.value, trace_id=trace_id,
                trace=trace,
            )

        if intent.intent == IntentType.UNSUPPORTED:
            trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                        data_summary={"terminal_state": "unsupported",
                                      "reason": intent.unsupported_reason})
            return self._build_result(
                None, req_id, "unsupported",
                intent=intent.intent.value, trace_id=trace_id,
                trace=trace,
            )

        # 6. 创建 pending memory
        base_version = committed.memory_version if committed is not None else 0
        memory = StructuredWorkMemory(
            conversation_id=conversation_id,
            request_id=req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            current_intent=intent.intent.value,
            state_status=MemoryStatus.PENDING,
            runtime_mode=runtime_mode,
            is_mock=True,
            llm_provider="mock",
            powerbi_provider="mock_powerbi",
            base_memory_version=base_version,
            memory_version=0,
        )
        await self.memory_repo.create_pending(memory, runtime_mode)

        # 7. TurnController
        controller = TurnController(self.config, request_id=req_id)
        # M0.4: TurnController 不再注入到 Gateway 共享字段
        # 通过 tool_gateway.execute(..., controller=controller) 显式传入
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()

        # 8. 生成 QueryPlan
        context["mock_scenario_key"] = scenario.query_plan_key
        plan_result = await self.llm.run(message, context, QueryPlan)
        query_plan: QueryPlan = plan_result.structured  # type: ignore[assignment]
        trace.record("plan_created", trace_id=trace_id, request_id=req_id)

        # 9. 通过 ToolGateway 获取 Schema（先转换到 PLAN_READY）
        controller.transition(TurnState.PLAN_READY)
        try:
            exec_ctx = ToolExecutionContext(
                trace_id=trace_id,
                request_id=req_id,
                conversation_id=conversation_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=user,
            )
            schema_input = SchemaInput(semantic_model_key=semantic_model_key)
            schema: SemanticModelSchema = await self.tool_gateway.execute(
                "get_semantic_model_schema",
                exec_ctx,
                schema_input,
                trace=trace,
                controller=controller,
            )
        except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as e:
            return await self._fail_turn(
                memory, req_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type=type(e).__name__,
                reason=str(e),
                stage="schema_fetch",
                trace_id=trace_id,
            )

        controller.record_tool_execution_succeeded()

        # 10. 验证 QueryPlan
        plan_validation = self.validator.validate_query_plan(query_plan, schema)
        if not plan_validation.is_valid:
            controller.set_failure_reason(str(plan_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.memory_repo.mark_failed(
                req_id, runtime_mode,
                reason=str(plan_validation.errors), stage="query_plan_validation"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                        data_summary={"reason": str(plan_validation.errors)})
            return self._build_result(
                memory, req_id, "validation_failed",
                intent=intent.intent.value, error_type="plan_validation_failed",
                trace_id=trace_id,
                trace=trace,
            )

        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)

        # 11. 生成 DAX
        context["mock_scenario_key"] = scenario.dax_key
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
                req_id, runtime_mode,
                reason=str(dax_validation.errors), stage="dax_validation"
            )
            return self._build_result(
                memory, req_id, "validation_failed",
                intent=intent.intent.value, error_type="dax_validation_failed",
                trace_id=trace_id,
                trace=trace,
            )

        controller.record_dax_valid()

        # 12. 通过 ToolGateway 执行 DAX
        try:
            exec_ctx = ToolExecutionContext(
                trace_id=trace_id,
                request_id=req_id,
                conversation_id=conversation_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=user,
            )
            query_result: QueryResult = await self.tool_gateway.execute(
                "execute_dax",
                exec_ctx,
                dax_req,
                trace=trace,
                controller=controller,
            )
        except ToolTimeoutError as e:
            return await self._fail_turn(
                memory, req_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type="timeout",
                reason=str(e),
                stage="dax_execution",
                trace_id=trace_id,
            )
        except (ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as e:
            return await self._fail_turn(
                memory, req_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type=type(e).__name__,
                reason=str(e),
                stage="dax_execution",
                trace_id=trace_id,
            )

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)

        # 13. 验证 QueryResult
        if query_result.error is not None:
            controller.set_failure_reason(query_result.error.message)
            controller.transition(TurnState.TOOL_FAILED)
            await self.memory_repo.mark_failed(
                req_id, runtime_mode,
                reason=query_result.error.message,
                stage="query_result_error"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                        error_type=query_result.error.type)
            return self._build_result(
                memory, req_id, "tool_failed",
                intent=intent.intent.value, error_type=query_result.error.type,
                trace_id=trace_id,
                trace=trace,
            )

        result_validation = self.validator.validate_query_result(query_result)
        if not result_validation.is_valid:
            controller.set_failure_reason(str(result_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.memory_repo.mark_failed(
                req_id, runtime_mode,
                reason=str(result_validation.errors), stage="result_validation"
            )
            return self._build_result(
                memory, req_id, "validation_failed",
                intent=intent.intent.value, error_type="result_validation_failed",
                trace_id=trace_id,
                trace=trace,
            )

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)

        # 14. 生成回答或报表
        if intent.intent == IntentType.DATA_QUESTION:
            context["mock_scenario_key"] = scenario.response_key
            answer_result = await self.llm.run(message, context, AnswerSpec)
            response_obj: AnswerSpec = answer_result.structured  # type: ignore[assignment]
            response_type = "answer"

            # 验证 Answer — source_mode 不一致必须为 error
            answer_validation = self.validator.validate_answer(response_obj, query_result)
            if not answer_validation.is_valid:
                controller.set_failure_reason(str(answer_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.memory_repo.mark_failed(
                    req_id, runtime_mode,
                    reason=str(answer_validation.errors), stage="answer_validation"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                            error_type="answer_validation_failed")
                return self._build_result(
                    memory, req_id, "response_failed",
                    intent=intent.intent.value, error_type="answer_validation_failed",
                    trace_id=trace_id,
                    trace=trace,
                )
        else:
            context["mock_scenario_key"] = scenario.response_key
            report_result = await self.llm.run(message, context, ReportSpec)
            report_spec: ReportSpec = report_result.structured  # type: ignore[assignment]

            report_validation = self.validator.validate_report(report_spec, schema, query_result)
            if not report_validation.is_valid:
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.memory_repo.mark_failed(
                    req_id, runtime_mode,
                    reason=str(report_validation.errors), stage="report_validation"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=req_id,
                            error_type="report_validation_failed")
                return self._build_result(
                    memory, req_id, "response_failed",
                    intent=intent.intent.value, error_type="report_validation_failed",
                    trace_id=trace_id,
                    trace=trace,
                )

            # 通过 ToolGateway 渲染报表
            try:
                exec_ctx = ToolExecutionContext(
                    trace_id=trace_id,
                    request_id=req_id,
                    conversation_id=conversation_id,
                    runtime_mode=runtime_mode,
                    intent=intent.intent,
                    user=user,
                )
                rendered: RenderedReport = await self.tool_gateway.execute(
                    "render_report",
                    exec_ctx,
                    report_spec,
                    trace=trace,
                    controller=controller,
                )
            except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                    ToolNotRegisteredError, ToolOutputValidationError) as e:
                return await self._fail_turn(
                    memory, req_id, controller, trace,
                    terminal_state=TurnState.RESPONSE_FAILED,
                    error_type=type(e).__name__,
                    reason=str(e),
                    stage="report_render",
                    trace_id=trace_id,
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
        # 使用 QueryResult 唯一 result_id，不用 scenario key
        memory.last_query_result_id = getattr(query_result, 'result_id', None) or str(uuid.uuid4())
        memory.last_result_summary = f"{query_result.row_count} rows"
        # 报表场景写入 last_report_id
        if response_type == "report":
            memory.last_report_id = rendered.report_id if rendered else None
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
            # Memory 冲突：pending 标记 failed
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.MEMORY_CONFLICT)
            await self.memory_repo.mark_failed(
                req_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            trace.record("memory_commit_rejected", trace_id=trace_id, request_id=req_id,
                        error_type="version_conflict")
            return self._build_result(
                memory, req_id, "memory_conflict", intent=intent.intent.value,
                error_type="version_conflict", trace_id=trace_id,
                trace=trace,
            )
        except MemoryCommitDeniedError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.RESPONSE_FAILED)
            await self.memory_repo.mark_failed(
                req_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            return self._build_result(
                memory, req_id, "response_failed", intent=intent.intent.value,
                error_type="memory_commit_denied", trace_id=trace_id,
                trace=trace,
            )

        controller.transition(TurnState.COMPLETED)
        trace.record("request_completed", trace_id=trace_id, request_id=req_id,
                    data_summary={"terminal_state": "completed"})

        # 工具序列唯一来源于 TraceRecorder
        return self._build_result(
            committed_memory, req_id, "completed",
            intent=intent.intent.value, response_type=response_type,
            trace_id=trace_id,
            state_changes={"memory_version": committed_memory.memory_version},
            trace=trace,
        )

    async def _fail_turn(
        self,
        memory: StructuredWorkMemory,
        request_id: str,
        controller: TurnController,
        trace: TraceRecorder,
        terminal_state: TurnState,
        error_type: str,
        reason: str,
        stage: str,
        trace_id: str = "",
    ) -> dict[str, Any]:
        """统一失败处理

        职责：
        - 设置 failure_reason
        - 执行合法状态转换
        - pending 存在时 mark_failed
        - 记录 trace 失败事件
        - 返回统一 TurnResult
        """
        controller.set_failure_reason(reason)
        # 执行状态转换 — 检查合法性后再转换
        if controller.is_terminal:
            # 已经处于终止状态，不再转换（例如 Schema 失败后又触发了 DAX 失败）
            pass
        elif not controller.can_continue:
            # 不可继续但也不是已知终止状态 — 记录异常
            trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                        error_type="TurnStateError",
                        data_summary={"reason": f"Unexpected non-terminal state {controller.state.value}"})
            raise RuntimeError(
                f"_fail_turn() called but controller in unexpected state "
                f"'{controller.state.value}' (not terminal, not continuable)"
            )
        else:
            try:
                controller.transition(terminal_state)
            except Exception:
                # 意外的非法状态转换 — 记录 Trace 后重新抛出
                trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                            error_type="TurnStateError",
                            data_summary={"reason": f"Illegal transition {controller.state.value} → {terminal_state.value}"})
                raise

        runtime_mode = memory.runtime_mode
        await self.memory_repo.mark_failed(
            request_id, runtime_mode, reason=reason, stage=stage
        )

        trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                    error_type=error_type,
                    data_summary={"reason": reason, "stage": stage})

        return self._build_result(
            memory, request_id, terminal_state.value,
            intent=memory.current_intent or "",
            error_type=error_type,
            trace_id=trace_id,
            trace=trace,
        )

    def _build_result(
        self,
        memory: Optional[StructuredWorkMemory],
        request_id: str,
        terminal_state: str,
        intent: str = "",
        response_type: str = "",
        error_type: Optional[str] = None,
        state_changes: Optional[dict[str, Any]] = None,
        trace_id: str = "",
        trace: Optional[TraceRecorder] = None,
    ) -> dict[str, Any]:
        """构建统一结果字典 — M0.4: trace 显式传入，工具序列来源于当前请求 TraceRecorder"""
        tool_sequence: list[str] = []
        if trace is not None:
            tool_sequence = trace.get_tool_sequence()

        if memory is not None:
            return {
                "request_id": request_id,
                "conversation_id": memory.conversation_id,
                "terminal_state": terminal_state,
                "intent": intent or memory.current_intent or "",
                "response_type": response_type,
                "error_type": error_type,
                "tool_sequence": tool_sequence,
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
                "tool_sequence": tool_sequence,
                "state_changes": state_changes or {},
                "memory_commit": False,
                "final_memory_version": None,
                "inherited_context": None,
                "allowed_tools": self.tool_gateway.list_tools(),
                "is_mock": True,
                "trace_id": trace_id,
            }
