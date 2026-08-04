"""DeepSeekTurnService — M1.5 DeepSeek + Mock Power BI 全链路

每个请求独立 LLMCallCollector + ObservedLLMProvider + Trace。
使用 RuntimeDataMode.REAL 空间，与 Mock 模式隔离。
复用 InMemoryMemoryRepository / ResultSnapshotStore / TraceRecorder / TurnController。

不复制 MockTurnService 执行管线。
不修改共享 Provider 实例方法。
DeepSeek 失败不回退 MockAgentRuntime。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from backend.app.application.turn_service_protocol import TurnServiceProtocol
from backend.app.config.settings import Settings
from backend.app.harness.models import HarnessConfig
from backend.app.harness.observability.llm_observer import (
    LLMCallCollector,
    LLMUsageSummary,
    ObservedLLMProvider,
)
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.deepseek_service import DeepSeekIntentService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMProvider, LLMTask
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
    UserContext,
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

    # ── 公共 API ──

    async def execute(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 DeepSeek Turn 流程"""

        # ── 统一生成 ID ──
        effective_conv_id = conversation_id or str(uuid.uuid4())
        effective_req_id = request_id or str(uuid.uuid4())
        runtime_mode = RuntimeDataMode.REAL

        # ── 计算请求指纹 ──
        fingerprint_hash = RequestFingerprint.compute_hash(
            message=message,
            client_conversation_id=conversation_id,
            semantic_model_key=semantic_model_key,
            effective_report_template_key=report_template_key,
            scenario=None,
            intent_key=None,
            powerbi_key=None,
        )

        trace_id = str(uuid.uuid4())
        trace = TraceRecorder(self.config)

        # ── 幂等检查 ──
        snapshot = await self.snapshot_store.get(effective_req_id, runtime_mode)
        if snapshot is not None:
            if snapshot.request_fingerprint_hash != fingerprint_hash:
                raise IdempotencyConflictError(
                    request_id=effective_req_id,
                    detail="request_id has already been used by a different request",
                )
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "duplicate"})
            return self._build_replay(snapshot, effective_req_id, trace_id)

        # ── Owner/Waiter 协调 ──
        for retry_attempt in range(3):
            claim_status, claim_future = await self.snapshot_store.claim(
                effective_req_id, runtime_mode, fingerprint_hash
            )
            if claim_status == IdempotencyClaimStatus.CONFLICT:
                raise IdempotencyConflictError(
                    request_id=effective_req_id,
                    detail="request_id has already been used by a different request",
                )
            elif claim_status == IdempotencyClaimStatus.WAITER:
                try:
                    await claim_future
                except Exception:
                    continue
                snapshot = await self.snapshot_store.get(effective_req_id, runtime_mode)
                if snapshot is not None:
                    new_trace_id = str(uuid.uuid4())
                    return self._build_replay(snapshot, effective_req_id, new_trace_id)
                continue
            elif claim_status == IdempotencyClaimStatus.OWNER:
                break
        else:
            raise IdempotencyCoordinationError(
                request_id=effective_req_id,
                detail="Unable to acquire execution right after retries",
            )

        # ── OWNER: 执行 ──
        try:
            result = await self._do_execute(
                message=message,
                effective_conv_id=effective_conv_id,
                effective_req_id=effective_req_id,
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
                runtime_mode=runtime_mode,
                trace=trace,
                trace_id=trace_id,
                fingerprint_hash=fingerprint_hash,
            )
            await self.snapshot_store.complete(effective_req_id, runtime_mode)
            return result
        except Exception:
            await self.snapshot_store.abort(effective_req_id, runtime_mode)
            raise

    # ── 核心执行管线 ──

    async def _do_execute(
        self,
        message: str,
        effective_conv_id: str,
        effective_req_id: str,
        semantic_model_key: str,
        report_template_key: Optional[str],
        runtime_mode: RuntimeDataMode,
        trace: TraceRecorder,
        trace_id: str,
        fingerprint_hash: str,
    ) -> dict[str, Any]:
        """Owner 执行完整 DeepSeek 管线"""

        trace.record("request_received", trace_id=trace_id, request_id=effective_req_id,
                     conversation_id=effective_conv_id)

        # ── 1. 每请求独立的 Collector + ObservedProvider ──
        collector = LLMCallCollector(
            input_cost_per_million=self.settings.deepseek_input_cost_per_million_tokens,
            output_cost_per_million=self.settings.deepseek_output_cost_per_million_tokens,
        )
        observed = ObservedLLMProvider(self.llm_provider, collector)

        # ── 2. 加载 committed memory（REAL 空间） ──
        committed = await self.memory_repo.get_latest_committed(
            effective_conv_id, runtime_mode
        )

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

        # ── 5. 创建 pending memory ──
        base_version = committed.memory_version if committed is not None else 0
        memory = StructuredWorkMemory(
            conversation_id=effective_conv_id,
            request_id=effective_req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            current_intent=intent.intent.value,
            state_status=MemoryStatus.PENDING,
            runtime_mode=runtime_mode,
            is_mock=False,
            llm_provider="deepseek",
            powerbi_provider="mock_powerbi",
            base_memory_version=base_version,
            memory_version=0,
        )
        await self.memory_repo.create_pending(memory, runtime_mode)

        # ── 6. TurnController ──
        controller = TurnController(self.config, request_id=effective_req_id)
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()

        # ── 7. 获取 Schema ──
        try:
            schema = await self.powerbi.get_semantic_model_schema(semantic_model_key)
        except Exception as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="schema_fetch", trace_id=trace_id,
                collector=collector,
            )
        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.PLAN_READY)

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
            await self.memory_repo.mark_failed(
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
            await self.memory_repo.mark_failed(
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

        # ── 10. 执行 Mock DAX 查询 ──
        fixture_key = "data_question" if intent.intent == IntentType.DATA_QUESTION else "report_generation"
        try:
            query_result = await self.powerbi.execute_fixture(dax_request, fixture_key)
        except Exception as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.TOOL_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="dax_execution", trace_id=trace_id,
                collector=collector,
            )

        # QueryResult 验证
        if query_result.error is not None:
            await self.memory_repo.mark_failed(
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
            await self.memory_repo.mark_failed(
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

            # 渲染报表
            try:
                rendered = RenderedReport(
                    report_id=str(uuid.uuid4()),
                    template_key=report_spec.template_key,
                    html=await self.report_renderer.render(report_spec),
                    source_mode="mock",
                )
            except Exception as e:
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
            await self.memory_repo.mark_failed(
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
            await self.memory_repo.mark_failed(
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
        """构建统一结果字典"""

        tool_sequence: list[str] = []
        if trace is not None:
            tool_sequence = trace.get_tool_sequence()

        # usage 摘要
        usage: Optional[LLMUsageSummary] = None
        if collector is not None:
            usage = collector.summary()

        result: dict[str, Any] = {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "terminal_state": terminal_state,
            "intent": intent,
            "response_type": response_type,
            "error_type": error_type,
            "tool_sequence": tool_sequence,
            "memory_commit": terminal_state == "completed",
            "trace_id": trace_id,
            "is_mock": is_mock,
            "source_mode": source_mode,
            "usage": usage,
            "allowed_tools": ["get_semantic_model_schema", "execute_dax", "render_report"],
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

    def _build_replay(
        self,
        snapshot: TurnResultSnapshot,
        request_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        """构建幂等重放响应"""
        report_dict: Optional[dict[str, Any]] = None
        if snapshot.report is not None:
            report_dict = {
                "report_id": snapshot.report.report_id,
                "template_key": snapshot.report.template_key,
                "html": snapshot.report.html,
            }

        return {
            "request_id": request_id,
            "conversation_id": snapshot.conversation_id,
            "terminal_state": "duplicate",
            "intent": snapshot.intent,
            "response_type": snapshot.response_type,
            "answer": snapshot.answer,
            "report": report_dict,
            "clarification_question": snapshot.clarification_question,
            "unsupported_reason": snapshot.unsupported_reason,
            "error_type": snapshot.error_type,
            "tool_sequence": [],
            "memory_commit": False,
            "trace_id": trace_id,
            "is_mock": snapshot.is_mock,
            "source_mode": "mock",
            "usage": None,
            "allowed_tools": snapshot.allowed_tools,
            "idempotent_replay": True,
            "replayed_request_id": snapshot.request_id,
        }

    async def _save_snapshot(
        self,
        result: dict[str, Any],
        runtime_mode: RuntimeDataMode,
        fingerprint_hash: str,
    ) -> None:
        """保存幂等快照"""
        report_snapshot: Optional[ReportResultSnapshot] = None
        if result.get("report"):
            rd = result["report"]
            report_snapshot = ReportResultSnapshot(
                report_id=rd.get("report_id", ""),
                template_key=rd.get("template_key", ""),
                html=rd.get("html", ""),
            )

        snapshot = TurnResultSnapshot(
            request_id=result.get("request_id", ""),
            conversation_id=result.get("conversation_id", ""),
            intent=result.get("intent", ""),
            response_type=result.get("response_type", ""),
            terminal_state=result.get("terminal_state", ""),
            answer=result.get("answer"),
            report=report_snapshot,
            clarification_question=result.get("clarification_question"),
            unsupported_reason=result.get("unsupported_reason"),
            error_type=result.get("error_type"),
            tool_sequence=result.get("tool_sequence", []),
            memory_commit=result.get("memory_commit", False),
            final_memory_version=None,
            is_mock=result.get("is_mock", False),
            trace_id=result.get("trace_id", ""),
            allowed_tools=result.get("allowed_tools", []),
            request_fingerprint_hash=fingerprint_hash,
        )
        await self.snapshot_store.save(snapshot, runtime_mode)
