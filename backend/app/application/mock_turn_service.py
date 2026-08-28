"""MockTurnService — M1.6.3 Mock 轮次服务（薄封装）

M1.6.3 更新：
- 共享 TurnPipeline 执行骨架统一 ID 生成、指纹、幂等、Snapshot
- MockAgentRuntime 替换为直接 MockLLMProvider（LLM 调用不再经过 AgentRuntime）
- ContextBuilder 和 ToolGateway 保持统一使用

M0.3.2—M1.0.1 历史修复保留在模块内部，不再逐一列举。
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from backend.app.application.turn_pipeline import TurnPipeline
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolNotRegisteredError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import HarnessConfig
from backend.app.harness.tool_registry import SchemaInput, create_default_tool_gateway
from backend.app.harness.runtime.tool_gateway import (
    ToolGateway,
)
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMRequest, LLMTask
from backend.app.llm.mock import MockLLMProvider
from backend.app.memory.models import (
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryRepository,
)
from backend.app.memory.request_fingerprint import (
    ScenarioFingerprint,
)
from backend.app.memory.result_snapshot import SnapshotRepository
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.query_plan.semantic_catalog import compute_schema_fingerprint
from backend.app.query_plan.template_catalog import (
    TemplateGroundingStatus,
)
from backend.app.report.base import ReportRenderer
from backend.app.report.mock import MockReportRenderer
from backend.app.report.resources import ReportArtifact, ReportRepository
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    DAXRequest,
    QueryPlan,
    QueryResult,
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


class MockTurnService:
    """Mock 轮次服务（M1.6.3 薄封装）

    M1.6.3: 共享 TurnPipeline 执行骨架，LLM 直接使用 MockLLMProvider。
    所有工具调用经过 ToolGateway。
    """

    def __init__(
        self,
        memory_repo: Optional[MemoryRepository] = None,
        llm_runtime: Any = None,  # M1.6.3: 向后兼容，内部提取 MockLLMProvider
        powerbi_adapter: Optional[MockPowerBIAdapter] = None,
        report_renderer: Optional[ReportRenderer] = None,
        report_repository: Optional[ReportRepository] = None,
        config: Optional[HarnessConfig] = None,
        llm_provider: Optional[MockLLMProvider] = None,  # M1.6.3: 新的直接注入方式
        snapshot_store: Optional[SnapshotRepository] = None,  # M4.1
    ):
        _repo = memory_repo or InMemoryMemoryRepository()
        self.powerbi = powerbi_adapter or MockPowerBIAdapter()
        self.report_renderer = report_renderer or MockReportRenderer()
        self._report_repository = report_repository
        self.config = config or HarnessConfig()

        # M1.6.3: LLM — 优先使用直接注入的 llm_provider，否则通过 llm_runtime
        if llm_provider is not None:
            self.llm_provider: MockLLMProvider = llm_provider
        elif llm_runtime is not None:
            # 从 llm_runtime 提取内部 MockLLMProvider（可能是 MockAgentRuntime 或 Spy）
            if hasattr(llm_runtime, "_llm") and isinstance(llm_runtime._llm, MockLLMProvider):
                self.llm_provider = llm_runtime._llm
            else:
                self.llm_provider = MockLLMProvider()
        else:
            self.llm_provider = MockLLMProvider()

        # 保留 llm_runtime 引用用于向后兼容（允许 Spy 拦截）
        self._llm_runtime = llm_runtime

        self.tool_gateway = self._build_tool_gateway()
        # Historical report fixtures stay isolated in Mock compatibility. They
        # are not M3 production availability declarations.
        self._user_context = UserContext(
            allowed_templates=sorted(MockReportRenderer.ALLOWED_TEMPLATES)
        )
        self.validator = ValidationService(
            allowed_templates=MockReportRenderer.ALLOWED_TEMPLATES
        )
        # M1.6.3.2: Service 不持有 memory_repo/SnapshotStore —
        #   TurnPipeline 是 Memory 和 Snapshot 的唯一写入者
        self.pipeline = TurnPipeline(
            config=self.config,
            memory_repo=_repo,
            snapshot_store=snapshot_store,
            report_repository=report_repository,
        )

    def _build_tool_gateway(self) -> ToolGateway:
        """构建 ToolGateway — M1.6.2 使用共享工具注册入口，超时/重试来自 HarnessConfig"""
        return create_default_tool_gateway(
            self.powerbi,
            self.report_renderer,
            self.config,
            self._report_repository,
        )

    # M1.6.4: Service 不再暴露 memory_repo 属性 —
    #   只读查询必须使用 TurnPipeline 公开只读方法：
    #   request_exists_in_memory() / get_memory_by_request_id()

    @property
    def llm(self) -> Any:
        """M1.6.3: 向后兼容 — 返回相容 MockAgentRuntime 接口的适配器

        旧测试通过 `svc.llm.run()` / `svc.llm.registered_tools` 等方式访问。
        如果 llm_runtime 已注入（如 SpyLLMRuntime），直接返回以保留拦截。
        """
        if self._llm_runtime is not None:
            return self._llm_runtime
        return _LLMProviderAdapter(self.llm_provider)

    async def execute(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
        llm_profile_key: Optional[str] = None,
        scenario: Optional[MockScenarioSelection] = None,
        intent_key: Optional[str] = None,
        powerbi_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 Turn 流程 — M1.6.3 委托给共享 TurnPipeline 骨架

        scenario=None 时使用 MockScenarioResolver 自动推断（API 路径）。
        显式传入 scenario 仅用于 Golden Cases 和内部测试。
        intent_key/powerbi_key 为向后兼容保留。
        """
        # ── 构建 Scenario 与 effective_report_template_key ──
        effective_template_key: Optional[str] = report_template_key
        resolved_scenario: Optional[MockScenarioSelection] = scenario

        if scenario is None:
            from backend.app.application.mock_scenario_resolver import (
                MockScenarioResolver,
            )
            if intent_key is not None or powerbi_key is not None:
                resolved_scenario = MockScenarioSelection(
                    intent_key=intent_key or "data_question",
                    query_plan_key=intent_key or "data_question",
                    dax_key=intent_key or "data_question",
                    powerbi_key=powerbi_key or intent_key or "data_question",
                    response_key=intent_key or "data_question",
                )
            else:
                resolution = MockScenarioResolver.resolve(
                    message=message,
                    report_template_key=report_template_key,
                )
                resolved_scenario = resolution.scenario
                effective_template_key = resolution.effective_report_template_key

        if llm_profile_key not in {None, "mock"}:
            raise KeyError(f"LLM profile '{llm_profile_key}' is unavailable in Mock mode")
        runtime_mode = RuntimeDataMode.MOCK if self.config.is_mock else RuntimeDataMode.REAL

        # ── 将 MockScenarioSelection 转换为 Memory 层 ScenarioFingerprint ──
        scenario_fp: Optional[ScenarioFingerprint] = None
        if resolved_scenario is not None:
            scenario_fp = ScenarioFingerprint(
                intent_key=resolved_scenario.intent_key,
                query_plan_key=resolved_scenario.query_plan_key,
                dax_key=resolved_scenario.dax_key,
                powerbi_key=resolved_scenario.powerbi_key,
                response_key=resolved_scenario.response_key,
            )

        # ── M1.6.3: 委托给共享 TurnPipeline 执行骨架 ──
        return await self.pipeline.execute(
            message=message,
            conversation_id=conversation_id,
            request_id=request_id,
            semantic_model_key=semantic_model_key,
            report_template_key=effective_template_key,
            runtime_mode=runtime_mode,
            is_mock=True,
            llm_provider_name="mock",
            llm_profile_key="mock",
            llm_model="mock-llm",
            llm_provider_protocol="mock",
            powerbi_provider_name="mock_powerbi",
            scenario_fingerprint_hash_inputs={
                "scenario": scenario_fp,
                "intent_key": intent_key,
                "powerbi_key": powerbi_key,
            },
            do_execute=self._do_execute,
            resolved_scenario=resolved_scenario,
            effective_template_key=effective_template_key,
        )

    async def _do_execute(
        self,
        message: str,
        effective_conv_id: str,
        effective_req_id: str,
        semantic_model_key: str,
        report_template_key: Optional[str],
        runtime_mode: RuntimeDataMode,
        is_mock: bool,
        llm_provider_name: str,
        powerbi_provider_name: str,
        trace: TraceRecorder,
        trace_id: str,
        fingerprint_hash: str,
        resolved_scenario: Optional[MockScenarioSelection] = None,
        effective_template_key: Optional[str] = None,
        controller: Optional[TurnController] = None,
        context: Optional[dict[str, Any]] = None,
        committed: Optional[StructuredWorkMemory] = None,
        pending_clarification: Optional[PendingClarificationContext] = None,
    ) -> dict[str, Any]:
        """Owner 执行 Mock LLM 管线（控制面由共享 TurnPipeline 骨架提供）"""
        # 确保 resolved_scenario 有效
        if resolved_scenario is None:
            resolved_scenario = MockScenarioSelection()
        if effective_template_key is None:
            effective_template_key = report_template_key
        if context is None:
            context = {}
        if controller is None:
            controller = TurnController(self.config, request_id=effective_req_id)

        trace.record("request_received", trace_id=trace_id, request_id=effective_req_id,
                     conversation_id=effective_conv_id)

        # M1.6.3.2: Memory 只读回退通过 TurnPipeline 只读方法
        if await self.pipeline.request_exists_in_memory(effective_req_id, runtime_mode):
            existing = await self.pipeline.get_memory_by_request_id(effective_req_id, runtime_mode)
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "duplicate"})
            return self._build_result(
                existing, effective_req_id, "duplicate", trace_id=trace_id,
                trace=trace, conversation_id=effective_conv_id,
            )

        # 4. 意图识别 — M1.6.3: 通过适配器（兼容旧 MockAgentRuntime 接口）
        context["mock_scenario_key"] = resolved_scenario.intent_key
        intent_result = await self.llm.run(message, context, IntentSpec)
        intent: IntentSpec = intent_result.structured  # type: ignore[assignment]
        trace.record("intent_classified", trace_id=trace_id, request_id=effective_req_id,
                     data_summary={"intent": intent.intent.value})

        # 5. clarification/unsupported → 直接终止，不创建 pending
        if intent.intent == IntentType.CLARIFICATION:
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "clarification_required",
                                      "reason": intent.clarification_question})
            return self._build_result(
                None, effective_req_id, "clarification_required",
                intent=intent.intent.value, trace_id=trace_id,
                trace=trace,
                response_type="clarification",
                clarification_question=intent.clarification_question,
                conversation_id=effective_conv_id,
            )

        if intent.intent == IntentType.UNSUPPORTED:
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "unsupported",
                                      "reason": intent.unsupported_reason})
            return self._build_result(
                None, effective_req_id, "unsupported",
                intent=intent.intent.value, trace_id=trace_id,
                trace=trace,
                response_type="unsupported",
                unsupported_reason=intent.unsupported_reason,
                conversation_id=effective_conv_id,
            )

        if intent.intent == IntentType.REPORT_GENERATION:
            template_grounding = self.pipeline.preflight_report_template(
                is_report_intent=True,
                message=message,
                report_template_key=effective_template_key,
            )
            if template_grounding.status != TemplateGroundingStatus.RESOLVED:
                trace.record(
                    "request_completed",
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    data_summary={
                        "terminal_state": "clarification_required",
                        "reason": template_grounding.method,
                    },
                )
                return self._build_result(
                    None,
                    effective_req_id,
                    "clarification_required",
                    intent=intent.intent.value,
                    response_type="clarification",
                    clarification_question=self.pipeline.REPORT_TEMPLATE_REQUIRED_MESSAGE,
                    trace_id=trace_id,
                    trace=trace,
                    conversation_id=effective_conv_id,
                )
            effective_template_key = template_grounding.canonical_key

        # 6. 创建 pending memory — M1.6.3.1: 委托给 TurnPipeline
        base_version = committed.memory_version if committed is not None else 0
        memory = await self.pipeline.create_pending_memory(
            conversation_id=effective_conv_id,
            request_id=effective_req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=effective_template_key,
            intent_value=intent.intent.value,
            runtime_mode=runtime_mode,
            is_mock=True,
            llm_provider_name="mock",
            powerbi_provider_name="mock_powerbi",
            base_version=base_version,
        )

        # 7. TurnController — M1.6.3.1: 由 TurnPipeline 提供
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()

        # 8. 生成 QueryPlan — M1.6.3: 通过适配器
        context["mock_scenario_key"] = resolved_scenario.query_plan_key
        plan_result = await self.llm.run(message, context, QueryPlan)
        query_plan: QueryPlan = plan_result.structured  # type: ignore[assignment]
        if intent.intent == IntentType.REPORT_GENERATION:
            query_plan = query_plan.model_copy(
                update={"requested_template": effective_template_key}
            )
        trace.record("plan_created", trace_id=trace_id, request_id=effective_req_id)

        # 9. 通过 ToolGateway 获取 Schema
        controller.transition(TurnState.PLAN_READY)
        try:
            exec_ctx = self.pipeline.create_tool_context(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=self._user_context,
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
                memory, effective_req_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type=type(e).__name__,
                reason=str(e),
                stage="schema_fetch",
                trace_id=trace_id,
                conversation_id=effective_conv_id,
            )

        controller.record_tool_execution_succeeded()

        # 10. 验证 QueryPlan
        plan_validation = self.validator.validate_query_plan(query_plan, schema)
        if not plan_validation.is_valid:
            controller.set_failure_reason(str(plan_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(plan_validation.errors), stage="query_plan_validation"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"reason": str(plan_validation.errors)})
            return self._build_result(
                memory, effective_req_id, "validation_failed",
                intent=intent.intent.value, error_type="plan_validation_failed",
                trace_id=trace_id,
                trace=trace,
                conversation_id=effective_conv_id,
            )

        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)

        # 11. 生成 DAX — M1.6.3: 通过适配器
        context["mock_scenario_key"] = resolved_scenario.dax_key
        dax_result = await self.llm.run(message, context, DAXRequest)
        dax_req: DAXRequest = dax_result.structured  # type: ignore[assignment]
        dax_req.semantic_model_key = semantic_model_key
        dax_req.request_id = resolved_scenario.powerbi_key
        dax_req.is_mock = True

        # 验证 DAX
        dax_validation = self.validator.validate_dax(dax_req)
        if not dax_validation.is_valid:
            controller.set_failure_reason(str(dax_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(dax_validation.errors), stage="dax_validation"
            )
            return self._build_result(
                memory, effective_req_id, "validation_failed",
                intent=intent.intent.value, error_type="dax_validation_failed",
                trace_id=trace_id,
                trace=trace,
                conversation_id=effective_conv_id,
            )

        controller.record_dax_valid()

        # 12. 通过 ToolGateway 执行 DAX
        try:
            exec_ctx = self.pipeline.create_tool_context(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=self._user_context,
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
                memory, effective_req_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type="timeout",
                reason=str(e),
                stage="dax_execution",
                trace_id=trace_id,
                conversation_id=effective_conv_id,
            )
        except (ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as e:
            return await self._fail_turn(
                memory, effective_req_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type=type(e).__name__,
                reason=str(e),
                stage="dax_execution",
                trace_id=trace_id,
                conversation_id=effective_conv_id,
            )

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)

        # 13. 验证 QueryResult
        if query_result.error is not None:
            controller.set_failure_reason(query_result.error.message)
            controller.transition(TurnState.TOOL_FAILED)
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=query_result.error.message,
                stage="query_result_error"
            )
            trace.record("request_failed", trace_id=trace_id, request_id=effective_req_id,
                        error_type=query_result.error.type)
            return self._build_result(
                memory, effective_req_id, "tool_failed",
                intent=intent.intent.value, error_type=query_result.error.type,
                trace_id=trace_id,
                trace=trace,
                conversation_id=effective_conv_id,
            )

        result_validation = self.validator.validate_query_result(query_result)
        if not result_validation.is_valid:
            controller.set_failure_reason(str(result_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(result_validation.errors), stage="result_validation"
            )
            return self._build_result(
                memory, effective_req_id, "validation_failed",
                intent=intent.intent.value, error_type="result_validation_failed",
                trace_id=trace_id,
                trace=trace,
                conversation_id=effective_conv_id,
            )

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)

        # 14. 生成回答或报表
        answer_text: Optional[str] = None
        report_data: Optional[dict[str, Any]] = None

        if intent.intent == IntentType.DATA_QUESTION:
            context["mock_scenario_key"] = resolved_scenario.response_key
            answer_result = await self.llm.run(message, context, AnswerSpec)
            response_obj: AnswerSpec = answer_result.structured  # type: ignore[assignment]
            response_type = "answer"
            answer_text = response_obj.answer

            answer_validation = self.validator.validate_answer(response_obj, query_result)
            if not answer_validation.is_valid:
                controller.set_failure_reason(str(answer_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.pipeline.mark_memory_failed(
                    effective_req_id, runtime_mode,
                    reason=str(answer_validation.errors), stage="answer_validation"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=effective_req_id,
                            error_type="answer_validation_failed")
                return self._build_result(
                    memory, effective_req_id, "response_failed",
                    intent=intent.intent.value, error_type="answer_validation_failed",
                    trace_id=trace_id,
                    trace=trace,
                    conversation_id=effective_conv_id,
                )
        else:
            context["mock_scenario_key"] = resolved_scenario.response_key
            report_result = await self.llm.run(message, context, ReportSpec)
            report_spec: ReportSpec = report_result.structured  # type: ignore[assignment]
            report_updates: dict[str, Any] = {
                "template_key": effective_template_key,
            }
            if effective_template_key == "sales_report":
                result_id = query_result.result_id or f"mock-{effective_req_id}"
                report_updates.update({
                    "contract_version": "mock-simple-report-v1",
                    "semantic_model_key": semantic_model_key,
                    "schema_fingerprint": compute_schema_fingerprint(schema),
                    "query_result_ids": [result_id],
                    "verified_fact_set_ids": [f"mock-vfs-{result_id}"],
                    "data_source": semantic_model_key,
                    "source_mode": "mock",
                })
            report_spec = report_spec.model_copy(update=report_updates)

            report_validation = self.validator.validate_report(report_spec, schema, query_result)
            if not report_validation.is_valid:
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.pipeline.mark_memory_failed(
                    effective_req_id, runtime_mode,
                    reason=str(report_validation.errors), stage="report_validation"
                )
                trace.record("request_failed", trace_id=trace_id, request_id=effective_req_id,
                            error_type="report_validation_failed")
                return self._build_result(
                    memory, effective_req_id, "response_failed",
                    intent=intent.intent.value, error_type="report_validation_failed",
                    trace_id=trace_id,
                    trace=trace,
                    conversation_id=effective_conv_id,
                )

            # 通过 ToolGateway 渲染报表
            try:
                exec_ctx = self.pipeline.create_tool_context(
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    conversation_id=effective_conv_id,
                    runtime_mode=runtime_mode,
                    intent=intent.intent,
                    user=self._user_context,
                )
                report_spec_with_ctx = report_spec.model_copy(update={
                    "conversation_id": effective_conv_id,
                    "request_id": effective_req_id,
                })
                rendered: ReportArtifact = await self.tool_gateway.execute(
                    "render_report",
                    exec_ctx,
                    report_spec_with_ctx,
                    trace=trace,
                    controller=controller,
                )
            except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                    ToolNotRegisteredError, ToolOutputValidationError) as e:
                return await self._fail_turn(
                    memory, effective_req_id, controller, trace,
                    terminal_state=TurnState.RESPONSE_FAILED,
                    error_type=type(e).__name__,
                    reason=str(e),
                    stage="report_render",
                    trace_id=trace_id,
                    conversation_id=effective_conv_id,
                )

            response_obj = report_spec
            response_type = "report"
            report_data = {
                "report_id": rendered.report_id,
                "template_key": rendered.template_key,
                "html": rendered.html,
                "contract_version": rendered.contract_version,
                "view_reference": rendered.view_reference,
                "download_reference": rendered.download_reference,
                "content_type": rendered.content_type,
                "content_hash": rendered.content_hash,
            }

        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)

        # 15. 提交前填充 Memory 全部分析字段
        memory.current_intent = intent.intent.value
        memory.analysis_goal = f"用户提问: {message}"
        memory.semantic_model_key = semantic_model_key
        memory.report_template_key = effective_template_key
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
        memory.last_query_result_id = getattr(query_result, 'result_id', None) or str(uuid.uuid4())
        memory.last_result_summary = f"{query_result.row_count} rows"
        if response_type == "report":
            memory.last_report_id = rendered.report_id if rendered else None
        memory.updated_at = datetime.utcnow()

        # 16. 原子提交 — M1.6.3.2: 唯一通过 TurnPipeline
        evidence = controller.build_commit_evidence()
        committed_memory, commit_error = await self.pipeline.commit_memory_safe(
            memory, evidence, controller, trace, trace_id, effective_req_id, runtime_mode
        )
        if commit_error is not None:
            terminal_state = "memory_conflict" if commit_error == "version_conflict" else "response_failed"
            return self._build_result(
                memory, effective_req_id, terminal_state, intent=intent.intent.value,
                error_type=commit_error, trace_id=trace_id,
                trace=trace,
                conversation_id=effective_conv_id,
            )

        controller.transition(TurnState.COMPLETED)
        trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                    data_summary={"terminal_state": "completed"})

        return self._build_result(
            committed_memory, effective_req_id, "completed",
            intent=intent.intent.value, response_type=response_type,
            trace_id=trace_id,
            state_changes={"memory_version": committed_memory.memory_version},
            trace=trace,
            answer_text=answer_text,
            report_data=report_data,
            conversation_id=effective_conv_id,
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
        conversation_id: str = "",
    ) -> dict[str, Any]:
        """统一失败处理 — M1.6.3.1: 委托控制面给 TurnPipeline"""

        # Transition controller
        controller.set_failure_reason(reason)
        if controller.is_terminal:
            pass
        elif not controller.can_continue:
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
                trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                            error_type="TurnStateError",
                            data_summary={"reason": f"Illegal transition {controller.state.value} → {terminal_state.value}"})
                raise

        # M1.6.3.1: Memory 失败标记委托给 TurnPipeline
        await self.pipeline.mark_memory_failed(
            request_id, memory.runtime_mode, reason=reason, stage=stage
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
            conversation_id=conversation_id,
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
        answer_text: Optional[str] = None,
        report_data: Optional[dict[str, Any]] = None,
        clarification_question: Optional[str] = None,
        unsupported_reason: Optional[str] = None,
        conversation_id: str = "",
    ) -> dict[str, Any]:
        """构建统一结果字典"""

        tool_sequence: list[str] = []
        if trace is not None:
            tool_sequence = trace.get_tool_sequence()

        effective_conv_id = conversation_id
        if memory is not None and memory.conversation_id:
            effective_conv_id = memory.conversation_id

        if memory is not None:
            result: dict[str, Any] = {
                "request_id": request_id,
                "conversation_id": effective_conv_id,
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
            result = {
                "request_id": request_id,
                "conversation_id": effective_conv_id,
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

        if answer_text is not None:
            result["answer"] = answer_text
        if report_data is not None:
            result["report"] = report_data
        if clarification_question is not None:
            result["clarification_question"] = clarification_question
        if unsupported_reason is not None:
            result["unsupported_reason"] = unsupported_reason

        return result

    # M1.6.3.2: _build_idempotent_replay 和 _save_snapshot 已移除
    #   — 统一由 TurnPipeline.execute() 管理幂等重放和快照保存


class _LLMProviderAdapter:
    """M1.6.3: 向后兼容适配器 — 将 MockLLMProvider 包装为旧 MockAgentRuntime 接口

    旧测试通过 svc.llm.run(message, context, output_type) 方式调用，
    本适配器转换为 MockLLMProvider.generate(request, output_type)。
    """

    def __init__(self, provider: MockLLMProvider):
        self._provider = provider
        self._tools: dict[str, Any] = {}

    async def run(
        self,
        user_input: str,
        context: dict[str, Any],
        output_type: type,
    ) -> Any:
        """兼容旧 MockAgentRuntime.run() 接口"""
        from backend.app.llm.base import LLMRequest
        task = LLMTask.INTENT_RECOGNITION
        type_name = output_type.__name__.lower()
        if "queryplan" in type_name:
            task = LLMTask.QUERY_PLAN
        elif "dax" in type_name.lower():
            task = LLMTask.DAX
        elif "answer" in type_name:
            task = LLMTask.ANSWER
        elif "report" in type_name:
            task = LLMTask.REPORT

        scenario_key = context.get("mock_scenario_key", "data_question")
        request = LLMRequest(
            messages=[{"role": "user", "content": user_input}],
            task=task,
            scenario_key=scenario_key,
        )
        response = await self._provider.generate(request, output_type)

        # 返回兼容旧 AgentRunResult 的对象
        class _CompatResult:
            def __init__(self, content, structured, finish_reason, usage):
                self.content = content
                self.structured = structured
                self.finish_reason = finish_reason
                self.usage = usage

        return _CompatResult(
            content=response.content,
            structured=response.structured,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )

    def register_tool(self, tool: Any) -> None:
        name = getattr(tool, "name", str(id(tool)))
        self._tools[name] = tool

    @property
    def registered_tools(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def is_mock(self) -> bool:
        return True
