"""DeepSeekTurnService — M1.6.3 DeepSeek + Mock Power BI 全链路

M1.6.3 更新：
- 真实工具执行统一通过 ToolGateway（create_default_tool_gateway）
- allowed_tools 来自 gateway.list_tools()，不再硬编码
- ContextBuilder 统一进入管线（输入长度限制、Memory 状态检查、runtime_mode 匹配）
- 工具白名单、Intent 权限、runtime_mode、超时和重试在 DeepSeek 路径真实生效

每个请求独立 LLMCallCollector + ObservedLLMProvider + Trace。
使用 RuntimeDataMode.REAL 空间，与 Mock 模式隔离。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from backend.app.application.turn_pipeline import TurnPipeline
from backend.app.application.turn_service_protocol import TurnServiceProtocol
from backend.app.config.settings import Settings
from backend.app.harness.errors import (
    ToolExecutionError,
    ToolNotRegisteredError,
    ToolOutputValidationError,
    ToolPolicyDeniedError,
    ToolTimeoutError,
)
from backend.app.harness.models import HarnessConfig
from backend.app.harness.observability.llm_observer import (
    LLMCallCollector,
    LLMUsageSummary,
    ObservedLLMProvider,
)
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.runtime.tool_gateway import (
    ToolGateway,
)
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.harness.tool_registry import (
    SchemaInput,
    TOOL_NAME_DAX,
    TOOL_NAME_RENDER,
    TOOL_NAME_SCHEMA,
    create_default_tool_gateway,
)
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.deepseek_service import DeepSeekIntentService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMProvider, LLMTask
from backend.app.memory.models import (
    MemoryCommitEvidence,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryCommitDeniedError,
    MemoryVersionConflictError,
)
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
    RequestFingerprint,
    ScenarioFingerprint,
)
from backend.app.memory.result_snapshot import (
    IdempotencyClaimStatus,
    ReportResultSnapshot,
    ResultSnapshotStore,
    TurnResultSnapshot,
)
from backend.app.powerbi.mock import MockPowerBIAdapter
from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService
from backend.app.dax.deepseek_service import DeepSeekDAXService
from backend.app.dax.safety import DAXSafetyValidator
from backend.app.answer.deepseek_service import DeepSeekAnswerService
from backend.app.report.deepseek_spec_service import DeepSeekReportSpecService
from backend.app.report.mock import MockReportRenderer
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    DAXRequest,
    QueryPlan,
    QueryResult,
    RenderedReport,
    ReportSpec,
    SemanticModelSchema,
)


class DeepSeekTurnService:
    """DeepSeek + Mock Power BI 轮次服务

    完整链路：Intent → Schema → QueryPlan → DAX → Mock QueryResult →
              Answer/ReportSpec → Mock Renderer → Memory Commit

    每个请求独立：
    - LLMCallCollector + ObservedLLMProvider（不污染并发）
    - TraceRecorder
    - TurnController

    使用 RuntimeDataMode.REAL 空间。
    """

    def __init__(
        self,
        memory_repo: InMemoryMemoryRepository,
        llm_provider: LLMProvider,
        powerbi_adapter: MockPowerBIAdapter,
        report_renderer: MockReportRenderer,
        settings: Settings,
        config: Optional[HarnessConfig] = None,
    ):
        if llm_provider.is_mock:
            raise ValueError("DeepSeekTurnService 要求非 Mock LLM Provider")

        self.memory_repo = memory_repo
        self.llm_provider = llm_provider
        self.powerbi = powerbi_adapter
        self.report_renderer = report_renderer
        self.settings = settings
        # M1.6.2: 禁止回退 Mock 配置。若未显式传入 config，从自身 settings 构建。
        self.config = config if config is not None else HarnessConfig.from_settings(settings)
        self.validator = ValidationService()
        self.snapshot_store = ResultSnapshotStore()
        # M1.6.3: ToolGateway 统一进入 DeepSeek 管线
        self.tool_gateway = self._build_tool_gateway()
        # M1.6.3: 共享 TurnPipeline 执行骨架（含 ContextBuilder、TurnController 生命周期）
        self.pipeline = TurnPipeline(
            config=self.config,
            memory_repo=self.memory_repo,
            snapshot_store=self.snapshot_store,
        )

    def _build_tool_gateway(self) -> ToolGateway:
        """构建 ToolGateway — M1.6.3 使用共享入口，与 Mock 路径完全一致"""
        return create_default_tool_gateway(self.powerbi, self.report_renderer, self.config)

    # ── 公共 API ──

    async def execute(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 DeepSeek Turn 流程 — 委托给共享 TurnPipeline 骨架"""

        return await self.pipeline.execute(
            message=message,
            conversation_id=conversation_id,
            request_id=request_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            runtime_mode=RuntimeDataMode.REAL,
            is_mock=False,
            llm_provider_name="deepseek",
            powerbi_provider_name="mock_powerbi",
            scenario_fingerprint_hash_inputs={
                "scenario": None,
                "intent_key": None,
                "powerbi_key": None,
            },
            do_execute=self._do_execute,
        )

    # ── 核心执行管线 ──

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
        controller: Optional[TurnController] = None,
        context: Optional[dict[str, Any]] = None,
        committed: Optional[StructuredWorkMemory] = None,
    ) -> dict[str, Any]:
        """Owner 执行 DeepSeek LLM 管线（控制面由共享 TurnPipeline 骨架提供）"""

        trace.record("request_received", trace_id=trace_id, request_id=effective_req_id,
                     conversation_id=effective_conv_id)

        # ── 默认值保护 ──
        if context is None:
            context = {}
        if controller is None:
            controller = TurnController(self.config, request_id=effective_req_id)

        # ── 1. 每请求独立的 Collector + ObservedProvider ──
        collector = LLMCallCollector(
            input_cost_per_million=self.settings.deepseek_input_cost_per_million_tokens,
            output_cost_per_million=self.settings.deepseek_output_cost_per_million_tokens,
        )
        observed = ObservedLLMProvider(self.llm_provider, collector)

        # ── 3. 意图识别 ──
        intent_service = DeepSeekIntentService(provider=observed, max_format_repairs=1)
        intent = await intent_service.recognize(
            user_input=message,
            committed_memory=committed.model_dump() if committed else None,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
        )
        trace.record("intent_classified", trace_id=trace_id, request_id=effective_req_id,
                     data_summary={"intent": intent.intent.value})

        # ── 4. clarification / unsupported 早期终止 ──
        if intent.intent == IntentType.CLARIFICATION:
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "clarification_required"})
            return self._build_result(
                effective_req_id, effective_conv_id, "clarification_required",
                intent=intent.intent.value, response_type="clarification",
                clarification_question=intent.clarification_question,
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock",
                collector=collector,
            )

        if intent.intent == IntentType.UNSUPPORTED:
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "unsupported"})
            return self._build_result(
                effective_req_id, effective_conv_id, "unsupported",
                intent=intent.intent.value, response_type="unsupported",
                unsupported_reason=intent.unsupported_reason,
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock",
                collector=collector,
            )

        # ── 5. 创建 pending memory — M1.6.3.1: 委托给 TurnPipeline ──
        base_version = committed.memory_version if committed is not None else 0
        memory = await self.pipeline.create_pending_memory(
            conversation_id=effective_conv_id,
            request_id=effective_req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            intent_value=intent.intent.value,
            runtime_mode=runtime_mode,
            is_mock=False,
            llm_provider_name="deepseek",
            powerbi_provider_name="mock_powerbi",
            base_version=base_version,
        )

        # ── 6. TurnController — M1.6.3.1: 由 TurnPipeline 提供 ──
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()

        # ── 7. 通过 ToolGateway 获取 Schema ──
        controller.transition(TurnState.PLAN_READY)
        try:
            exec_ctx = self.pipeline.create_tool_context(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
            )
            schema_input = SchemaInput(semantic_model_key=semantic_model_key)
            schema: SemanticModelSchema = await self.tool_gateway.execute(
                TOOL_NAME_SCHEMA,
                exec_ctx,
                schema_input,
                trace=trace,
                controller=controller,
            )
        except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="schema_fetch", trace_id=trace_id,
                collector=collector,
            )

        controller.record_tool_execution_succeeded()

        # ── 8. QueryPlan 生成与验证 ──
        try:
            qp_service = DeepSeekQueryPlanService(provider=observed, max_format_repairs=1)
            query_plan = await qp_service.generate(
                user_input=message, intent=intent, schema=schema,
                committed_memory=committed.model_dump() if committed else None,
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
            )
        except Exception as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.VALIDATION_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="query_plan_generation", trace_id=trace_id,
                collector=collector,
            )

        # QueryPlan 验证
        plan_validation = self.validator.validate_query_plan(query_plan, schema)
        if not plan_validation.is_valid:
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(plan_validation.errors), stage="query_plan_validation"
            )
            controller.set_failure_reason(str(plan_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            return self._build_result(
                effective_req_id, effective_conv_id, "validation_failed",
                intent=intent.intent.value, error_type="query_plan_validation_failed",
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock", collector=collector,
            )

        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)
        trace.record("query_plan_validated", trace_id=trace_id, request_id=effective_req_id)

        # ── 9. DAX 生成与验证 ──
        try:
            dax_service = DeepSeekDAXService(provider=observed, max_dax_repairs=1)
            dax_request = await dax_service.generate(
                query_plan=query_plan, schema=schema,
                semantic_model_key=semantic_model_key,
                request_id=effective_req_id,
            )
        except Exception as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.VALIDATION_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="dax_generation", trace_id=trace_id,
                collector=collector,
            )

        # DAX 安全验证
        safety = DAXSafetyValidator()
        safety_result = safety.validate(dax_request.dax, schema)
        if not safety_result.is_valid:
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(safety_result.errors), stage="dax_safety"
            )
            controller.set_failure_reason(str(safety_result.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            return self._build_result(
                effective_req_id, effective_conv_id, "validation_failed",
                intent=intent.intent.value, error_type="dax_validation_failed",
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock", collector=collector,
            )

        controller.record_dax_valid()
        trace.record("dax_validated", trace_id=trace_id, request_id=effective_req_id,
                     data_summary={"is_read_only": safety_result.is_valid})

        # ── 10. 通过 ToolGateway 执行 DAX 查询 ──
        fixture_key = "data_question" if intent.intent == IntentType.DATA_QUESTION else "report_generation"
        # M1.6.3: fixture_key 通过私有属性传给 MockPowerBIAdapter.execute_dax
        dax_request._fixture_key = fixture_key  # type: ignore[attr-defined]
        try:
            exec_ctx = self.pipeline.create_tool_context(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
            )
            query_result: QueryResult = await self.tool_gateway.execute(
                TOOL_NAME_DAX,
                exec_ctx,
                dax_request,
                trace=trace,
                controller=controller,
            )
        except ToolTimeoutError as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED, error_type="timeout",
                reason=str(e), stage="dax_execution", trace_id=trace_id,
                collector=collector,
            )
        except (ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="dax_execution", trace_id=trace_id,
                collector=collector,
            )

        # QueryResult 验证
        if query_result.error is not None:
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=query_result.error.message, stage="query_result_error"
            )
            controller.set_failure_reason(query_result.error.message)
            controller.transition(TurnState.TOOL_FAILED)
            return self._build_result(
                effective_req_id, effective_conv_id, "tool_failed",
                intent=intent.intent.value, error_type=query_result.error.type,
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock", collector=collector,
            )

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)

        result_validation = self.validator.validate_query_result(query_result)
        if not result_validation.is_valid:
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(result_validation.errors), stage="result_validation"
            )
            return self._build_result(
                effective_req_id, effective_conv_id, "validation_failed",
                intent=intent.intent.value, error_type="query_result_invalid",
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock", collector=collector,
            )

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)
        trace.record("query_result_validated", trace_id=trace_id, request_id=effective_req_id)

        # 确保 source_mode 始终为 mock
        query_result.source_mode = "mock"

        # ── 11. 生成 Answer 或 ReportSpec ──
        answer_text: Optional[str] = None
        report_data: Optional[dict[str, Any]] = None
        response_type: str = ""

        if intent.intent == IntentType.DATA_QUESTION:
            response_type = "answer"
            try:
                answer_service = DeepSeekAnswerService(provider=observed, max_repairs=1)
                response_obj: AnswerSpec = await answer_service.generate(
                    user_input=message, intent=intent, query_plan=query_plan,
                    query_result=query_result, schema=schema,
                    request_id=effective_req_id,
                )
            except Exception as e:
                return await self._fail_result(
                    memory, effective_req_id, effective_conv_id, controller, trace,
                    terminal_state=TurnState.RESPONSE_FAILED, error_type=type(e).__name__,
                    reason=str(e), stage="answer_generation", trace_id=trace_id,
                    collector=collector,
                )

            answer_text = response_obj.answer
            answer_validation = self.validator.validate_answer_strict(response_obj, query_result)
            if not answer_validation.is_valid:
                await self.memory_repo.mark_failed(
                    effective_req_id, runtime_mode,
                    reason=str(answer_validation.errors), stage="answer_validation"
                )
                controller.set_failure_reason(str(answer_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                return self._build_result(
                    effective_req_id, effective_conv_id, "response_failed",
                    intent=intent.intent.value, error_type="answer_validation_failed",
                    trace=trace, trace_id=trace_id, is_mock=False,
                    source_mode="mock", collector=collector,
                )
            trace.record("answer_validated", trace_id=trace_id, request_id=effective_req_id)
        else:
            response_type = "report"
            try:
                report_service = DeepSeekReportSpecService(provider=observed, max_repairs=1)
                report_spec: ReportSpec = await report_service.generate(
                    user_input=message, intent=intent, query_plan=query_plan,
                    query_result=query_result, schema=schema,
                    template_key=report_template_key or "",
                    allowed_templates=None,
                    request_id=effective_req_id,
                )
            except Exception as e:
                return await self._fail_result(
                    memory, effective_req_id, effective_conv_id, controller, trace,
                    terminal_state=TurnState.RESPONSE_FAILED, error_type=type(e).__name__,
                    reason=str(e), stage="report_generation", trace_id=trace_id,
                    collector=collector,
                )

            # M1.6.3: 通过 ToolGateway 渲染报表
            try:
                exec_ctx = self.pipeline.create_tool_context(
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    conversation_id=effective_conv_id,
                    runtime_mode=runtime_mode,
                    intent=intent.intent,
                )
                rendered: RenderedReport = await self.tool_gateway.execute(
                    TOOL_NAME_RENDER,
                    exec_ctx,
                    report_spec,
                    trace=trace,
                    controller=controller,
                )
            except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                    ToolNotRegisteredError, ToolOutputValidationError) as e:
                return await self._fail_result(
                    memory, effective_req_id, effective_conv_id, controller, trace,
                    terminal_state=TurnState.RESPONSE_FAILED, error_type=type(e).__name__,
                    reason=str(e), stage="report_render", trace_id=trace_id,
                    collector=collector,
                )

            report_data = {
                "report_id": rendered.report_id,
                "template_key": rendered.template_key,
                "html": rendered.html,
            }
            response_obj = report_spec

            report_validation = self.validator.validate_report_strict(report_spec, query_result)
            if not report_validation.is_valid:
                await self.memory_repo.mark_failed(
                    effective_req_id, runtime_mode,
                    reason=str(report_validation.errors), stage="report_validation"
                )
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                return self._build_result(
                    effective_req_id, effective_conv_id, "response_failed",
                    intent=intent.intent.value, error_type="report_validation_failed",
                    trace=trace, trace_id=trace_id, is_mock=False,
                    source_mode="mock", collector=collector,
                )
            trace.record("report_spec_validated", trace_id=trace_id, request_id=effective_req_id)

        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)

        # ── 12. 填充 Memory 分析字段 ──
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
        memory.last_dax = dax_request.dax
        memory.last_query_result_id = query_result.result_id
        memory.last_result_summary = f"{query_result.row_count} rows"
        if response_type == "report" and report_data is not None:
            memory.last_report_id = report_data["report_id"]
        memory.updated_at = datetime.utcnow()

        # ── 13. 原子提交 Memory ──
        evidence = controller.build_commit_evidence()
        try:
            committed_memory = await self.memory_repo.commit(memory, evidence)
            controller.record_version_matches()
            controller.transition(TurnState.MEMORY_COMMITTED)
            trace.record("memory_committed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"version": committed_memory.memory_version})
        except MemoryVersionConflictError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.MEMORY_CONFLICT)
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            return self._build_result(
                effective_req_id, effective_conv_id, "memory_conflict",
                intent=intent.intent.value, error_type="version_conflict",
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock", collector=collector,
            )
        except MemoryCommitDeniedError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.RESPONSE_FAILED)
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            return self._build_result(
                effective_req_id, effective_conv_id, "response_failed",
                intent=intent.intent.value, error_type="memory_commit_denied",
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode="mock", collector=collector,
            )

        controller.transition(TurnState.COMPLETED)
        trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                    data_summary={"terminal_state": "completed"})

        # ── 14. 保存快照 ──
        result = self._build_result(
            effective_req_id, effective_conv_id, "completed",
            intent=intent.intent.value, response_type=response_type,
            trace=trace, trace_id=trace_id, is_mock=False,
            source_mode="mock", collector=collector,
            answer_text=answer_text,
            report_data=report_data,
        )
        await self._save_snapshot(result, runtime_mode, fingerprint_hash)
        return result

    # ── 辅助方法 ──

    async def _fail_result(
        self,
        memory: StructuredWorkMemory,
        request_id: str,
        conversation_id: str,
        controller: TurnController,
        trace: TraceRecorder,
        terminal_state: TurnState,
        error_type: str,
        reason: str,
        stage: str,
        trace_id: str,
        collector: LLMCallCollector,
    ) -> dict[str, Any]:
        """统一失败处理"""
        controller.set_failure_reason(reason)
        try:
            controller.transition(terminal_state)
        except Exception:
            pass

        runtime_mode = memory.runtime_mode
        try:
            await self.memory_repo.mark_failed(
                request_id, runtime_mode, reason=reason, stage=stage
            )
        except Exception:
            pass

        trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                    error_type=error_type,
                    data_summary={"reason": reason, "stage": stage})

        return self._build_result(
            request_id, conversation_id, terminal_state.value,
            intent=memory.current_intent or "",
            error_type=error_type,
            trace=trace, trace_id=trace_id, is_mock=False,
            source_mode="mock", collector=collector,
        )

    # M1.6.3: 辅助方法委托给共享 TurnPipeline，保证统一行为

    def _build_result(
        self,
        request_id: str,
        conversation_id: str,
        terminal_state: str,
        intent: str = "",
        response_type: str = "",
        error_type: Optional[str] = None,
        trace: Optional[TraceRecorder] = None,
        trace_id: str = "",
        is_mock: bool = False,
        source_mode: str = "mock",
        collector: Optional[LLMCallCollector] = None,
        answer_text: Optional[str] = None,
        report_data: Optional[dict[str, Any]] = None,
        clarification_question: Optional[str] = None,
        unsupported_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """构建统一结果字典 — 委托给共享 TurnPipeline"""
        usage: Optional[LLMUsageSummary] = None
        if collector is not None:
            usage = collector.summary()

        return self.pipeline.build_result(
            request_id=request_id,
            conversation_id=conversation_id,
            terminal_state=terminal_state,
            intent=intent,
            response_type=response_type,
            error_type=error_type,
            trace=trace,
            trace_id=trace_id,
            is_mock=is_mock,
            source_mode=source_mode,
            allowed_tools=self.tool_gateway.list_tools(),
            answer_text=answer_text,
            report_data=report_data,
            clarification_question=clarification_question,
            unsupported_reason=unsupported_reason,
            usage=usage,
        )

    def _build_replay(
        self,
        snapshot: TurnResultSnapshot,
        request_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        """构建幂等重放响应 — 委托给共享 TurnPipeline"""
        return self.pipeline.build_replay(snapshot, request_id, trace_id)

    async def _save_snapshot(
        self,
        result: dict[str, Any],
        runtime_mode: RuntimeDataMode,
        fingerprint_hash: str,
    ) -> None:
        """保存幂等快照 — 委托给共享 TurnPipeline"""
        await self.pipeline._save_snapshot(result, runtime_mode, fingerprint_hash)
