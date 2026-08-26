"""DeepSeekTurnService — 共享 DeepSeek + PowerBIAdapter 全链路

M1.6.3 更新：
- 真实工具执行统一通过 ToolGateway（create_default_tool_gateway）
- allowed_tools 来自 gateway.list_tools()，不再硬编码
- ContextBuilder 统一进入管线（输入长度限制、Memory 状态检查、runtime_mode 匹配）
- 工具白名单、Intent 权限、runtime_mode、超时和重试在 DeepSeek 路径真实生效

每个请求独立 LLMCallCollector + ObservedLLMProvider + Trace。
使用 RuntimeDataMode.REAL 空间，与 Mock 模式隔离。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional

from backend.app.application.turn_pipeline import TurnPipeline
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
    TOOL_NAME_MEMBERS,
    SchemaInput,
    TOOL_NAME_DAX,
    TOOL_NAME_RENDER,
    TOOL_NAME_SCHEMA,
    create_default_tool_gateway,
)
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.deepseek_service import DeepSeekIntentService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.intent.service import IntentRecognitionError
from backend.app.intent.unsupported_policy import (
    CapabilityClass,
    classify_capability,
    deterministic_unsupported_reason,
    should_defer_unsupported_to_grounding,
)
from backend.app.llm.base import LLMProvider, LLMTask
from backend.app.memory.models import (
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)
from backend.app.memory.repository import (
    InMemoryMemoryRepository,
    MemoryRepository,
)
from backend.app.report.capability import (
    ANALYSIS_SECTION_ORDER,
    KPI_SECTION_ORDER,
    SECTION_REQUIREMENTS,
)
from backend.app.report.deepseek_report_intent_service import (
    DeepSeekReportIntentService,
)
from backend.app.report.intent import resolve_report_intent
from backend.app.report.plan import ReportPlanError, ReportPlanner
from backend.app.powerbi.base import PowerBIAdapter
from backend.app.query_plan.deepseek_service import (
    DeepSeekQueryPlanService,
    QueryPlanError,
)
from backend.app.query_plan.clarification import PendingClarificationService
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    GroundingStatus,
    SemanticGroundingService,
)
from backend.app.query_plan.semantic_catalog import (
    GlossaryCatalogError,
    SemanticCatalogBuilder,
)
from backend.app.query_plan.state_transition import (
    StateTransitionService,
    TurnInheritancePolicy,
)
from backend.app.query_plan.template_catalog import (
    DEFAULT_TEMPLATE_CATALOG,
    TemplateGroundingStatus,
)
from backend.app.dax.deepseek_service import DeepSeekDAXService
from backend.app.dax.builder import DAXBuildError, DeterministicDAXBuilder
from backend.app.dax.safety import DAXSafetyValidator
from backend.app.answer.deepseek_service import DeepSeekAnswerService
from backend.app.facts import (
    FactBoundedAnswerBuilder,
    FactBoundedReportBuilder,
    FactOutputValidator,
    FactVerificationError,
    FactType,
    VerifiedFactSet,
    VerifiedFactSetBuilder,
)
from backend.app.report.deepseek_spec_service import DeepSeekReportSpecService
from backend.app.report.assembly import (
    SalesReportAssemblyError,
    SalesReportDataAssembler,
    SalesReportSpecBuilder,
)
from backend.app.report.base import ReportRenderer
from backend.app.report.contracts import (
    ReportContractError,
    ReportContractValidator,
    ReportDataPlanBuilder,
)
from backend.app.report.resources import (
    ReportArtifact,
    ReportRepository,
)
from backend.app.presentation.builder import StructuredPresentationBuilder
from backend.app.presentation.localization import (
    BoundedLLMDisplayTranslator,
    DisplayLocalization,
    DisplayLocalizationError,
    DisplayLocalizationService,
    JsonDisplayLocalizationRegistry,
)
from backend.app.presentation.models import PresentationEnvelope
from backend.app.schemas.data_contracts import (
    AnswerSpec,
    ColumnMembersRequest,
    ColumnMembersResult,
    DAXRequest,
    QueryPlan,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
    UserContext,
)


class DeepSeekTurnService:
    """DeepSeek + 可注入 PowerBIAdapter 轮次服务

    完整链路：Intent → Schema → QueryPlan → DAX → QueryResult →
              Answer/ReportSpec → Renderer → Memory Commit

    每个请求独立：
    - LLMCallCollector + ObservedLLMProvider（不污染并发）
    - TraceRecorder
    - TurnController

    使用 RuntimeDataMode.REAL 空间。
    """

    def __init__(
        self,
        memory_repo: MemoryRepository,
        llm_provider: LLMProvider,
        powerbi_adapter: PowerBIAdapter,
        report_renderer: ReportRenderer,
        settings: Settings,
        config: Optional[HarnessConfig] = None,
        report_repository: ReportRepository | None = None,
        snapshot_store: Optional[SnapshotRepository] = None,  # M4.1
    ):
        if llm_provider.is_mock:
            raise ValueError("DeepSeekTurnService 要求非 Mock LLM Provider")

        self.llm_provider = llm_provider
        self.powerbi = powerbi_adapter
        self.report_renderer = report_renderer
        self._report_repository = report_repository
        self.settings = settings
        # M1.6.2: 禁止回退 Mock 配置。若未显式传入 config，从自身 settings 构建。
        self.config = config if config is not None else HarnessConfig.from_settings(settings)
        self._source_mode = "mock" if powerbi_adapter.is_mock else "real"
        # M1.6.3: ToolGateway 统一进入 DeepSeek 管线
        self.tool_gateway = self._build_tool_gateway()
        # M1.6.3.2: Service 不持有 memory_repo/SnapshotStore —
        #   TurnPipeline 是 Memory 和 Snapshot 的唯一写入者
        self.pipeline = TurnPipeline(
            config=self.config,
            memory_repo=memory_repo,
            snapshot_store=snapshot_store,
            report_repository=report_repository,
        )

    def _build_tool_gateway(self) -> ToolGateway:
        """构建 ToolGateway — M1.6.3 使用共享入口，与 Mock 路径完全一致"""
        return create_default_tool_gateway(
            self.powerbi,
            self.report_renderer,
            self.config,
            self._report_repository,
        )

    # M1.6.4: Service 不再暴露 memory_repo 属性 —
    #   只读查询必须使用 TurnPipeline 公开只读方法：
    #   request_exists_in_memory() / get_memory_by_request_id()

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
            powerbi_provider_name=self.powerbi.provider_name,
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
        pending_clarification: Optional[PendingClarificationContext] = None,
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

        capability = classify_capability(message)
        semantic_audit: dict[str, Any] = {
            "request_id": effective_req_id,
            "conversation_id": effective_conv_id,
            "capability_decision": capability.value,
            "dax_executed": False,
            "memory_committed": False,
        }
        trace.record(
            "capability_decision",
            trace_id=trace_id,
            request_id=effective_req_id,
            data_summary={"decision": capability.value},
        )

        unsupported_reason = deterministic_unsupported_reason(message)
        if unsupported_reason is not None:
            await self.pipeline.clear_pending_clarification(
                effective_conv_id, runtime_mode
            )
            trace.record(
                "request_completed",
                trace_id=trace_id,
                request_id=effective_req_id,
                data_summary={
                    "terminal_state": "unsupported",
                    "policy": "deterministic_preflight",
                },
            )
            return self._build_result(
                effective_req_id,
                effective_conv_id,
                "unsupported",
                intent=IntentType.UNSUPPORTED.value,
                response_type="unsupported",
                unsupported_reason=unsupported_reason,
                trace=trace,
                trace_id=trace_id,
                is_mock=False,
                source_mode=self._source_mode,
                collector=collector,
                execution_audit={
                    **semantic_audit,
                    "unsupported_preflight": True,
                    "committed_memory_mutated": False,
                },
            )

        commit_base = committed
        semantic_committed = committed
        if (
            committed is not None
            and committed.semantic_model_key != semantic_model_key
        ):
            semantic_committed = None
            await self.pipeline.clear_pending_clarification(
                effective_conv_id, runtime_mode
            )
            pending_clarification = None
            trace.record(
                "semantic_model_context_reset",
                trace_id=trace_id,
                request_id=effective_req_id,
                data_summary={"reason": "semantic_model_key_changed"},
            )
        request_user_context = UserContext(
            allowed_semantic_models=[semantic_model_key],
            allowed_templates=list(DEFAULT_TEMPLATE_CATALOG.allowed_keys),
        )
        request_validator = ValidationService(
            allowed_semantic_models=[semantic_model_key],
            allowed_templates=DEFAULT_TEMPLATE_CATALOG.allowed_keys,
        )

        if (
            pending_clarification is not None
            and PendingClarificationService.should_abandon(message)
        ):
            await self.pipeline.clear_pending_clarification(
                effective_conv_id, runtime_mode
            )
            pending_clarification = None

        # ── 3. 意图识别 ──
        intent_service = DeepSeekIntentService(provider=observed, max_format_repairs=1)
        try:
            intent = await intent_service.recognize(
                user_input=message,
                committed_memory=(
                    semantic_committed.model_dump() if semantic_committed else None
                ),
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
            )
        except IntentRecognitionError:
            if (
                capability != CapabilityClass.READ_ANALYSIS
                or report_template_key is not None
                or any(term in message for term in ("报告", "周报", "概览", "总览"))
            ):
                raise
            intent = IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=0.0,
                normalized_question=message.strip(),
            )
            semantic_audit["intent_fallback"] = True
            trace.record(
                "intent_language_draft_unavailable",
                trace_id=trace_id,
                request_id=effective_req_id,
                data_summary={"fallback": "deterministic_grounding_only"},
            )
        trace.record("intent_classified", trace_id=trace_id, request_id=effective_req_id,
                     data_summary={"intent": intent.intent.value})

        # ── 4. unsupported 可按产品契约早停；Real clarification 只作为
        # linguistic diagnostic。数据/报表范围内的 canonical semantic
        # authority 统一交给后续 Grounding，不再做 Measure-only 特判。
        if intent.intent == IntentType.UNSUPPORTED:
            if should_defer_unsupported_to_grounding(
                message,
                intent,
                committed=semantic_committed,
                pending=pending_clarification,
                report_template_key=report_template_key,
            ):
                provisional_intent = (
                    IntentType.REPORT_GENERATION
                    if report_template_key is not None
                    or any(term in message for term in ("报告", "周报", "概览", "总览"))
                    else IntentType.DATA_QUESTION
                )
                intent = intent.model_copy(update={
                    "intent": provisional_intent,
                    "unsupported_reason": None,
                })
                trace.record(
                    "intent_unsupported_deferred_to_grounding",
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    data_summary={"provisional_intent": provisional_intent.value},
                )
            else:
                await self.pipeline.clear_pending_clarification(
                    effective_conv_id, runtime_mode
                )
                trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                            data_summary={"terminal_state": "unsupported"})
                return self._build_result(
                    effective_req_id, effective_conv_id, "unsupported",
                    intent=intent.intent.value, response_type="unsupported",
                    unsupported_reason=intent.unsupported_reason,
                    trace=trace, trace_id=trace_id, is_mock=False,
                    source_mode=self._source_mode,
                    collector=collector,
                    execution_audit={
                        **semantic_audit,
                        "committed_memory_mutated": False,
                    },
                )

        if intent.intent == IntentType.CLARIFICATION and not self.powerbi.is_mock:
            provisional_intent = (
                IntentType.REPORT_GENERATION
                if report_template_key is not None
                or any(term in message for term in ("报告", "周报", "概览", "总览"))
                else IntentType.DATA_QUESTION
            )
            intent = intent.model_copy(update={
                "intent": provisional_intent,
                "needs_clarification": False,
                "clarification_question": None,
            })
            trace.record(
                "intent_clarification_deferred_to_grounding",
                trace_id=trace_id,
                request_id=effective_req_id,
                data_summary={"provisional_intent": provisional_intent.value},
            )

        schema: SemanticModelSchema | None = None
        exec_ctx: Any = None
        controller_prepared = False

        if intent.intent == IntentType.CLARIFICATION:
            if controller_prepared:
                controller.transition(TurnState.CLARIFICATION_REQUIRED)
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "clarification_required"})
            return self._build_result(
                effective_req_id, effective_conv_id, "clarification_required",
                intent=intent.intent.value, response_type="clarification",
                clarification_question=intent.clarification_question,
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode=self._source_mode,
                collector=collector,
            )

        # ── 5. 创建 pending memory — M1.6.3.1: 委托给 TurnPipeline ──
        base_version = commit_base.memory_version if commit_base is not None else 0
        memory = await self.pipeline.create_pending_memory(
            conversation_id=effective_conv_id,
            request_id=effective_req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            intent_value=intent.intent.value,
            runtime_mode=runtime_mode,
            is_mock=False,
            llm_provider_name="deepseek",
            powerbi_provider_name=powerbi_provider_name,
            base_version=base_version,
        )

        # ── 6. TurnController — M1.6.3.1: 由 TurnPipeline 提供 ──
        if not controller_prepared:
            controller.transition(TurnState.INTENT_CLASSIFIED)
            controller.record_intent_valid()

        # ── 7. 通过 ToolGateway 获取 Schema ──
        if not controller_prepared:
            controller.transition(TurnState.PLAN_READY)
        try:
            if exec_ctx is None:
                exec_ctx = self.pipeline.create_tool_context(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=request_user_context,
            )
            if schema is None:
                schema_input = SchemaInput(semantic_model_key=semantic_model_key)
                schema = await self.tool_gateway.execute(
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
                terminal_state=TurnState.TOOL_FAILED,
                error_type=getattr(e, "error_type", type(e).__name__),
                reason=str(e), stage="schema_fetch", trace_id=trace_id,
                collector=collector,
            )

        controller.record_tool_execution_succeeded()

        # ── 8. QueryPlan 生成与验证 ──
        try:
            qp_service = DeepSeekQueryPlanService(provider=observed, max_format_repairs=1)
            query_plan = await qp_service.generate(
                user_input=message, intent=intent, schema=schema,
                committed_memory=(
                    semantic_committed.model_dump() if semantic_committed else None
                ),
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
                enforce_semantic_grounding=not self.powerbi.is_mock,
            )
        except QueryPlanError as e:
            if intent.intent != IntentType.DATA_QUESTION:
                return await self._fail_result(
                    memory,
                    effective_req_id,
                    effective_conv_id,
                    controller,
                    trace,
                    terminal_state=TurnState.VALIDATION_FAILED,
                    error_type=type(e).__name__,
                    reason=str(e),
                    stage="query_plan_generation",
                    trace_id=trace_id,
                    collector=collector,
                )
            query_plan = QueryPlan(
                normalized_question=message.strip(),
                semantic_model_key=semantic_model_key,
            )
            semantic_audit["query_plan_fallback"] = True
            trace.record(
                "query_plan_language_draft_unavailable",
                trace_id=trace_id,
                request_id=effective_req_id,
                data_summary={"fallback": "deterministic_grounding_only"},
            )
        except Exception as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.VALIDATION_FAILED, error_type=type(e).__name__,
                reason=str(e), stage="query_plan_generation", trace_id=trace_id,
                collector=collector,
            )

        template_grounding = DEFAULT_TEMPLATE_CATALOG.ground(
            message,
            weak_requested_template=query_plan.requested_template,
            explicit_template_key=report_template_key,
            required=intent.intent == IntentType.REPORT_GENERATION,
        )
        if template_grounding.status in {
            TemplateGroundingStatus.AMBIGUOUS,
            TemplateGroundingStatus.UNRESOLVED,
            TemplateGroundingStatus.CONFIG_CONFLICT,
        }:
            await self.pipeline.mark_memory_failed(
                effective_req_id,
                runtime_mode,
                reason=template_grounding.status.value,
                stage="template_grounding",
            )
            controller.set_failure_reason(template_grounding.status.value)
            controller.transition(TurnState.CLARIFICATION_REQUIRED)
            return self._build_result(
                effective_req_id,
                effective_conv_id,
                "clarification_required",
                intent=intent.intent.value,
                response_type="clarification",
                clarification_question="请明确要使用的报表模板。",
                trace=trace,
                trace_id=trace_id,
                is_mock=False,
                source_mode=self._source_mode,
                collector=collector,
            )

        if intent.intent == IntentType.REPORT_GENERATION and not self.powerbi.is_mock:
            return await self._execute_sales_report_turn(
                message=message,
                memory=memory,
                intent=intent,
                schema=schema,
                template_key=template_grounding.canonical_key or "",
                effective_req_id=effective_req_id,
                effective_conv_id=effective_conv_id,
                runtime_mode=runtime_mode,
                controller=controller,
                trace=trace,
                trace_id=trace_id,
                collector=collector,
            )

        # ── 8.1 Business Semantic Grounding ──
        # QueryPlan LLM 在此仅是语言草稿；canonical semantic slots 只能由
        # validated catalog + runtime members + deterministic transition 决定。
        catalog = None
        if not self.powerbi.is_mock:
            try:
                catalog = SemanticCatalogBuilder().build(
                    schema,
                    glossary_scope_key=self.settings.powerbi_local_semantic_model_key,
                )
                if pending_clarification is not None and (
                    pending_clarification.semantic_model_key != semantic_model_key
                    or pending_clarification.schema_fingerprint
                    != catalog.schema_fingerprint
                    or pending_clarification.runtime_mode != runtime_mode
                    or pending_clarification.intent != intent.intent.value
                ):
                    await self.pipeline.clear_pending_clarification(
                        effective_conv_id, runtime_mode
                    )
                    pending_clarification = None
                grounding_service = SemanticGroundingService(
                    catalog,
                    selector=BoundedLLMObjectSelector(observed),
                )

                async def _member_lookup(
                    field: Any, limit: int
                ) -> ColumnMembersResult:
                    return await self.tool_gateway.execute(
                        TOOL_NAME_MEMBERS,
                        exec_ctx,
                        ColumnMembersRequest(
                            semantic_model_key=semantic_model_key,
                            table_name=field.table_name,
                            field_name=field.canonical_name,
                            limit=limit,
                        ),
                        trace=trace,
                        controller=controller,
                    )

                grounding = await grounding_service.ground(
                    message,
                    intent,
                    query_plan,
                    semantic_committed,
                    _member_lookup,
                    pending=pending_clarification,
                )
                grounded_delta = grounding.delta
                explicit_slots: list[str] = []
                if grounded_delta is not None:
                    if grounded_delta.measures is not None:
                        explicit_slots.append("measure")
                    if grounded_delta.dimensions is not None:
                        explicit_slots.append("dimensions")
                    if grounded_delta.filters or grounded_delta.clear_filters:
                        explicit_slots.append("filters")
                    if grounded_delta.time_specified or grounded_delta.clear_time:
                        explicit_slots.append("time")
                    if (
                        grounded_delta.sort_specified
                        or grounded_delta.top_n_specified
                        or grounded_delta.clear_sort
                        or grounded_delta.clear_top_n
                    ):
                        explicit_slots.append("ranking")
                if any(item.role == "filter_field" for item in grounding.object_results):
                    explicit_slots.append("filters")
                if grounding.member_results:
                    explicit_slots.append("filters")
                for item in grounding.object_results:
                    if item.status == GroundingStatus.NOT_MENTIONED:
                        continue
                    if item.role == "measure":
                        explicit_slots.append("measure")
                    elif item.role in {"dimension", "ranking_dimension"}:
                        explicit_slots.append("dimensions")
                    elif item.role == "date_field":
                        explicit_slots.append("time")
                semantic_audit.update({
                    "current_explicit_slots": sorted(set(explicit_slots)),
                    "object_grounding_status": [
                        {
                            "role": item.role,
                            "status": item.status.value,
                            "method": item.method,
                            "candidate_count": len(item.candidate_ids),
                        }
                        for item in grounding.object_results
                    ],
                    "member_grounding_status": [
                        {
                            "field_id": item.field.object_id,
                            "status": item.status.value,
                            "method": item.method,
                        }
                        for item in grounding.member_results
                    ],
                })
                if not grounding.pending_eligible:
                    await self.pipeline.clear_pending_clarification(
                        effective_conv_id, runtime_mode
                    )
                    await self.pipeline.mark_memory_failed(
                        effective_req_id,
                        runtime_mode,
                        reason="semantic_capability_unsupported",
                        stage="semantic_grounding",
                    )
                    controller.set_failure_reason("semantic_capability_unsupported")
                    controller.transition(TurnState.CLARIFICATION_REQUIRED)
                    trace.record(
                        "semantic_capability_unsupported",
                        trace_id=trace_id,
                        request_id=effective_req_id,
                        data_summary={"status": grounding.status.value},
                    )
                    return self._build_result(
                        effective_req_id,
                        effective_conv_id,
                        "clarification_required",
                        intent=intent.intent.value,
                        response_type="clarification",
                        clarification_question=grounding.clarification_question,
                        trace=trace,
                        trace_id=trace_id,
                        is_mock=False,
                        source_mode=self._source_mode,
                        collector=collector,
                        execution_audit={
                            **semantic_audit,
                            "pending_clarification": False,
                            "committed_memory_mutated": False,
                            "schema_fingerprint": catalog.schema_fingerprint,
                        },
                    )
                clarification_merge = None
                if (
                    pending_clarification is not None
                    or grounding.status != GroundingStatus.RESOLVED
                    or grounding.delta is None
                ):
                    clarification_merge = PendingClarificationService().merge(
                        previous=pending_clarification,
                        outcome=grounding,
                        user_input=message,
                        conversation_id=effective_conv_id,
                        request_id=effective_req_id,
                        semantic_model_key=semantic_model_key,
                        schema_fingerprint=catalog.schema_fingerprint,
                        runtime_mode=runtime_mode,
                        intent=intent.intent.value,
                        committed=semantic_committed,
                    )
                if clarification_merge is not None and not clarification_merge.complete:
                    await self.pipeline.save_pending_clarification(
                        clarification_merge.context, runtime_mode
                    )
                    await self.pipeline.mark_memory_failed(
                        effective_req_id,
                        runtime_mode,
                        reason="pending_clarification_incomplete",
                        stage="semantic_grounding",
                    )
                    controller.set_failure_reason("pending_clarification_incomplete")
                    controller.transition(TurnState.CLARIFICATION_REQUIRED)
                    trace.record(
                        "semantic_grounding_clarification",
                        trace_id=trace_id,
                        request_id=effective_req_id,
                        data_summary={
                            "status": grounding.status.value,
                            "chain_id": clarification_merge.context.chain_id,
                            "missing_slots": clarification_merge.context.missing_slots,
                        },
                    )
                    return self._build_result(
                        effective_req_id,
                        effective_conv_id,
                        "clarification_required",
                        intent=intent.intent.value,
                        response_type="clarification",
                        clarification_question=clarification_merge.clarification_question,
                        trace=trace,
                        trace_id=trace_id,
                        is_mock=False,
                        source_mode=self._source_mode,
                        collector=collector,
                        execution_audit={
                            **semantic_audit,
                            "pending_clarification": True,
                            "clarification_chain_id": (
                                clarification_merge.context.chain_id
                            ),
                            "missing_slots": (
                                clarification_merge.context.missing_slots
                            ),
                            "resolved_slots": sorted(
                                clarification_merge.context.slot_provenance
                            ),
                            "committed_memory_mutated": False,
                            "schema_fingerprint": catalog.schema_fingerprint,
                        },
                    )
                transition_delta = grounding.delta
                transition_base = semantic_committed
                if clarification_merge is not None:
                    if clarification_merge.executable_delta is None:
                        raise ValueError("clarification_complete_without_delta")
                    transition_delta = clarification_merge.executable_delta
                    # A clarification chain owns only explicitly verified slots;
                    # unrelated committed business slots cannot leak into it.
                    transition_base = None
                    await self.pipeline.clear_pending_clarification(
                        effective_conv_id, runtime_mode
                    )
                if transition_delta is None:
                    raise ValueError("semantic_grounding_delta_missing")
                inheritance = TurnInheritancePolicy.decide(
                    message,
                    intent,
                    transition_delta,
                    transition_base,
                )
                if inheritance.requires_clarification or inheritance.mode is None:
                    await self.pipeline.mark_memory_failed(
                        effective_req_id,
                        runtime_mode,
                        reason=inheritance.reason,
                        stage="inheritance_policy",
                    )
                    controller.set_failure_reason(inheritance.reason)
                    controller.transition(TurnState.CLARIFICATION_REQUIRED)
                    return self._build_result(
                        effective_req_id,
                        effective_conv_id,
                        "clarification_required",
                        intent=intent.intent.value,
                        response_type="clarification",
                        clarification_question=(
                            "请说明这是一个独立问题，还是要修改上一轮条件。"
                        ),
                        trace=trace,
                        trace_id=trace_id,
                        is_mock=False,
                        source_mode=self._source_mode,
                        collector=collector,
                        execution_audit={
                            **semantic_audit,
                            "inheritance_policy": inheritance.reason,
                            "committed_memory_mutated": False,
                        },
                    )
                transition = StateTransitionService().merge(
                    query_plan,
                    transition_delta,
                    transition_base,
                    canonical_template_key=template_grounding.canonical_key,
                    inheritance_mode=inheritance.mode,
                )
                query_plan = transition.query_plan
                inherited_slots = [
                    slot
                    for slot, transition_value in (
                        ("measure", transition.transitions.measure),
                        ("dimensions", transition.transitions.dimension),
                        ("time", transition.transitions.time),
                        ("sort", transition.transitions.sort),
                        ("top_n", transition.transitions.top_n),
                    )
                    if transition_value.value == "KEEP"
                    and slot not in explicit_slots
                ]
                if (
                    transition_base is not None
                    and not grounded_delta.filters
                    and not grounded_delta.clear_filters
                ):
                    inherited_slots.append("filters")
                canonical_plan_hash = hashlib.sha256(
                    query_plan.model_dump_json().encode("utf-8")
                ).hexdigest()
                semantic_audit.update({
                    "inherited_slots": sorted(set(inherited_slots)),
                    "canonical_plan_hash": canonical_plan_hash,
                })
                trace.record(
                    "semantic_grounding_resolved",
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    data_summary={
                        "authority": "semantic_catalog",
                        "inheritance_mode": inheritance.mode.value,
                        "inheritance_reason": inheritance.reason,
                        "intent_disagreement_count": len(
                            grounding.intent_disagreements
                        ),
                        "measure_transition": transition.transitions.measure.value,
                        "dimension_transition": transition.transitions.dimension.value,
                        "time_transition": transition.transitions.time.value,
                        "sort_transition": transition.transitions.sort.value,
                        "top_n_transition": transition.transitions.top_n.value,
                        "filter_transitions": [
                            item.value for item in transition.transitions.filters
                        ],
                        **semantic_audit,
                    },
                )
            except GlossaryCatalogError as e:
                return await self._fail_result(
                    memory,
                    effective_req_id,
                    effective_conv_id,
                    controller,
                    trace,
                    terminal_state=TurnState.VALIDATION_FAILED,
                    error_type="semantic_catalog_invalid",
                    reason=e.code,
                    stage="semantic_catalog",
                    trace_id=trace_id,
                    collector=collector,
                )
            except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                    ToolNotRegisteredError, ToolOutputValidationError) as e:
                return await self._fail_result(
                    memory,
                    effective_req_id,
                    effective_conv_id,
                    controller,
                    trace,
                    terminal_state=TurnState.TOOL_FAILED,
                    error_type=getattr(e, "error_type", type(e).__name__),
                    reason=str(e),
                    stage="member_grounding",
                    trace_id=trace_id,
                    collector=collector,
                )
            except Exception as e:
                return await self._fail_result(
                    memory,
                    effective_req_id,
                    effective_conv_id,
                    controller,
                    trace,
                    terminal_state=TurnState.VALIDATION_FAILED,
                    error_type="semantic_grounding_failed",
                    reason=type(e).__name__,
                    stage="semantic_grounding",
                    trace_id=trace_id,
                    collector=collector,
                )

        # QueryPlan 验证
        plan_validation = request_validator.validate_query_plan(
            query_plan,
            schema,
            enforce_semantic_grounding=not self.powerbi.is_mock,
        )
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
                source_mode=self._source_mode, collector=collector,
            )

        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)
        trace.record("query_plan_validated", trace_id=trace_id, request_id=effective_req_id)

        # ── 9. DAX 生成与验证 ──
        try:
            if self.powerbi.is_mock:
                # Historical Mock compatibility only. Real canonical execution
                # is exclusively plan + runtime schema -> deterministic builder.
                dax_service = DeepSeekDAXService(
                    provider=observed, max_dax_repairs=1
                )
                dax_request = await dax_service.generate(
                    query_plan=query_plan,
                    schema=schema,
                    semantic_model_key=semantic_model_key,
                    request_id=effective_req_id,
                )
            else:
                dax_request = DeterministicDAXBuilder().build(
                    query_plan,
                    schema,
                    request_id=effective_req_id,
                    timeout_seconds=self.settings.powerbi_query_timeout_seconds,
                )
        except Exception as e:
            return await self._fail_result(
                memory, effective_req_id, effective_conv_id, controller, trace,
                terminal_state=TurnState.VALIDATION_FAILED,
                error_type=(e.code if isinstance(e, DAXBuildError) else type(e).__name__),
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
                source_mode=self._source_mode, collector=collector,
            )

        if not self.powerbi.is_mock:
            consistency_result = request_validator.validate_dax_query_plan_consistency(
                dax_request,
                query_plan,
                schema,
            )
            if not consistency_result.is_valid:
                await self.pipeline.mark_memory_failed(
                    effective_req_id,
                    runtime_mode,
                    reason=str(consistency_result.errors),
                    stage="dax_semantic_consistency",
                )
                controller.set_failure_reason(str(consistency_result.errors))
                controller.transition(TurnState.VALIDATION_FAILED)
                return self._build_result(
                    effective_req_id,
                    effective_conv_id,
                    "validation_failed",
                    intent=intent.intent.value,
                    error_type="dax_semantic_consistency_failed",
                    trace=trace,
                    trace_id=trace_id,
                    is_mock=False,
                    source_mode=self._source_mode,
                    collector=collector,
                )

        controller.record_dax_valid()
        trace.record("dax_validated", trace_id=trace_id, request_id=effective_req_id,
                     data_summary={"is_read_only": safety_result.is_valid})

        # ── 10. 通过 ToolGateway 执行 DAX 查询 ──
        fixture_key = "data_question" if intent.intent == IntentType.DATA_QUESTION else "report_generation"
        # Fixture 选择只属于 Mock Adapter；Real Adapter 只接收标准 DAXRequest。
        if self.powerbi.is_mock:
            dax_request._fixture_key = fixture_key  # type: ignore[attr-defined]
        try:
            exec_ctx = self.pipeline.create_tool_context(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=request_user_context,
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
                source_mode=self._source_mode, collector=collector,
            )

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)

        result_validation = request_validator.validate_query_result(
            query_result,
            expected_source_mode=self._source_mode,
        )
        if not result_validation.is_valid:
            await self.pipeline.mark_memory_failed(
                effective_req_id, runtime_mode,
                reason=str(result_validation.errors), stage="result_validation"
            )
            return self._build_result(
                effective_req_id, effective_conv_id, "validation_failed",
                intent=intent.intent.value, error_type="query_result_invalid",
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode=self._source_mode, collector=collector,
            )

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)
        trace.record(
            "query_result_validated",
            trace_id=trace_id,
            request_id=effective_req_id,
            data_summary={"source_mode": query_result.source_mode},
        )

        verified_facts: VerifiedFactSet | None = None
        if not self.powerbi.is_mock:
            try:
                verified_facts = VerifiedFactSetBuilder().build(
                    query_plan, query_result
                )
            except FactVerificationError as e:
                return await self._fail_result(
                    memory,
                    effective_req_id,
                    effective_conv_id,
                    controller,
                    trace,
                    terminal_state=TurnState.VALIDATION_FAILED,
                    error_type=e.code,
                    reason=e.code,
                    stage="verified_fact_set",
                    trace_id=trace_id,
                    collector=collector,
                )
            trace.record(
                "verified_fact_set_built",
                trace_id=trace_id,
                request_id=effective_req_id,
                data_summary={
                    "fact_set_id": verified_facts.fact_set_id,
                    "fact_count": len(verified_facts.facts),
                    "row_count": verified_facts.row_count,
                    "truncated": verified_facts.truncated,
                },
            )

        # ── 11. 生成 Answer 或 ReportSpec ──
        answer_text: Optional[str] = None
        report_data: Optional[dict[str, Any]] = None
        response_type: str = ""
        display_bindings: dict[str, DisplayLocalization] | None = None

        if intent.intent == IntentType.DATA_QUESTION:
            response_type = "answer"
            try:
                if verified_facts is not None:
                    if catalog is not None:
                        verified_fields = {
                            field
                            for fact in verified_facts.facts
                            if fact.fact_type in {
                                FactType.SCALAR_METRIC,
                                FactType.GROUPED_METRIC,
                                FactType.RANKING,
                                FactType.MAXIMUM,
                                FactType.MINIMUM,
                            }
                            for field in fact.source_fields
                        }
                        presentation_fields = [
                            field
                            for field in query_result.columns
                            if field in verified_fields
                        ]
                        registry = JsonDisplayLocalizationRegistry(
                            self.settings.presentation_localization_registry_path
                        )
                        localization = DisplayLocalizationService(
                            catalog,
                            registry=registry,
                            translator=BoundedLLMDisplayTranslator(observed),
                        )
                        try:
                            resolved = await localization.resolve_fields(
                                presentation_fields,
                                locale="zh-CN",
                                table_hints=query_plan.dimension_tables,
                            )
                        except DisplayLocalizationError as exc:
                            trace.record(
                                "presentation_localization_fallback",
                                trace_id=trace_id,
                                request_id=effective_req_id,
                                data_summary={"reason": str(exc)},
                            )
                            resolved = await DisplayLocalizationService(
                                catalog
                            ).resolve_fields(
                                presentation_fields,
                                locale="zh-CN",
                                table_hints=query_plan.dimension_tables,
                            )
                        display_bindings = dict(
                            zip(presentation_fields, resolved)
                        )
                        trace.record(
                            "presentation_localization_resolved",
                            trace_id=trace_id,
                            request_id=effective_req_id,
                            data_summary={
                                "field_count": len(resolved),
                                "sources": sorted({
                                    item.source.value for item in resolved
                                }),
                                "schema_identity": (
                                    resolved[0].schema_identity
                                    if resolved else None
                                ),
                            },
                        )
                    response_obj = FactBoundedAnswerBuilder().build(
                        query_plan,
                        query_result,
                        verified_facts,
                        display_bindings=display_bindings,
                    )
                else:
                    answer_service = DeepSeekAnswerService(
                        provider=observed, max_repairs=1
                    )
                    response_obj = await answer_service.generate(
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
            answer_validation = request_validator.validate_answer_strict(response_obj, query_result)
            if answer_validation.is_valid and verified_facts is not None:
                fact_errors = FactOutputValidator().validate_answer(
                    response_obj, verified_facts
                )
                if fact_errors:
                    answer_validation = answer_validation.model_copy(update={
                        "valid": False,
                        "errors": [*answer_validation.errors, *fact_errors],
                        "error_code": "answer_fact_validation_failed",
                    })
            if not answer_validation.is_valid:
                await self.pipeline.mark_memory_failed(
                    effective_req_id, runtime_mode,
                    reason=str(answer_validation.errors), stage="answer_validation"
                )
                controller.set_failure_reason(str(answer_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                return self._build_result(
                    effective_req_id, effective_conv_id, "response_failed",
                    intent=intent.intent.value, error_type="answer_validation_failed",
                    trace=trace, trace_id=trace_id, is_mock=False,
                    source_mode=self._source_mode, collector=collector,
                )
            trace.record("answer_validated", trace_id=trace_id, request_id=effective_req_id)
        else:
            response_type = "report"
            try:
                if verified_facts is not None:
                    report_spec = FactBoundedReportBuilder().build(
                        query_plan, query_result, verified_facts
                    )
                else:
                    report_service = DeepSeekReportSpecService(
                        provider=observed, max_repairs=1
                    )
                    report_spec = await report_service.generate(
                        user_input=message, intent=intent, query_plan=query_plan,
                        query_result=query_result, schema=schema,
                        template_key=query_plan.requested_template or "",
                        allowed_templates=set(DEFAULT_TEMPLATE_CATALOG.allowed_keys),
                        request_id=effective_req_id,
                    )
            except Exception as e:
                return await self._fail_result(
                    memory, effective_req_id, effective_conv_id, controller, trace,
                    terminal_state=TurnState.RESPONSE_FAILED, error_type=type(e).__name__,
                    reason=str(e), stage="report_generation", trace_id=trace_id,
                    collector=collector,
                )

            report_validation = request_validator.validate_report_strict(
                report_spec, query_result
            )
            if report_validation.is_valid and verified_facts is not None:
                fact_errors = FactOutputValidator().validate_report(
                    report_spec, verified_facts, query_result
                )
                if fact_errors:
                    report_validation = report_validation.model_copy(update={
                        "valid": False,
                        "errors": [*report_validation.errors, *fact_errors],
                        "error_code": "report_fact_validation_failed",
                    })
            if not report_validation.is_valid:
                await self.pipeline.mark_memory_failed(
                    effective_req_id, runtime_mode,
                    reason=str(report_validation.errors), stage="report_validation"
                )
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                return self._build_result(
                    effective_req_id, effective_conv_id, "response_failed",
                    intent=intent.intent.value,
                    error_type="report_validation_failed",
                    trace=trace, trace_id=trace_id, is_mock=False,
                    source_mode=self._source_mode, collector=collector,
                )

            # Only a fact-validated ReportSpec may reach the renderer.
            try:
                exec_ctx = self.pipeline.create_tool_context(
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    conversation_id=effective_conv_id,
                    runtime_mode=runtime_mode,
                    intent=intent.intent,
                    user=request_user_context,
                )
                report_spec_with_ctx = report_spec.model_copy(update={
                    "conversation_id": effective_conv_id,
                    "request_id": effective_req_id,
                })
                rendered: ReportArtifact = await self.tool_gateway.execute(
                    TOOL_NAME_RENDER,
                    exec_ctx,
                    report_spec_with_ctx,
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
                "contract_version": rendered.contract_version,
                "view_reference": rendered.view_reference,
                "download_reference": rendered.download_reference,
                "content_type": rendered.content_type,
                "content_hash": rendered.content_hash,
            }
            response_obj = report_spec
            trace.record("report_spec_validated", trace_id=trace_id, request_id=effective_req_id)

        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)

        # ── 12. 填充 Memory 分析字段 ──
        memory.current_intent = intent.intent.value
        memory.analysis_goal = f"用户提问: {message}"
        memory.semantic_model_key = semantic_model_key
        memory.report_template_key = query_plan.requested_template
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

        # ── 13. 原子提交 Memory — M1.6.3.2: 唯一通过 TurnPipeline ──
        evidence = controller.build_commit_evidence()
        committed_memory, commit_error = await self.pipeline.commit_memory_safe(
            memory, evidence, controller, trace, trace_id, effective_req_id, runtime_mode
        )
        if commit_error is not None:
            terminal_state = "memory_conflict" if commit_error == "version_conflict" else "response_failed"
            return self._build_result(
                effective_req_id, effective_conv_id, terminal_state,
                intent=intent.intent.value, error_type=commit_error,
                trace=trace, trace_id=trace_id, is_mock=False,
                source_mode=self._source_mode, collector=collector,
            )

        controller.transition(TurnState.COMPLETED)
        semantic_audit.update({
            "dax_executed": True,
            "memory_committed": True,
        })
        trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                    data_summary={
                        "terminal_state": "completed",
                        **semantic_audit,
                    })

        # ── 14. 构建结果（Snapshot 由 TurnPipeline.execute() 统一保存） ──
        presentation: PresentationEnvelope | None = None
        if verified_facts is not None and answer_text:
            presentation = StructuredPresentationBuilder.build_answer(
                query_plan,
                query_result,
                verified_facts,
                answer_text,
                display_bindings=display_bindings,
            )
        elif report_data is not None:
            presentation = StructuredPresentationBuilder.build_report(
                report_data["report_id"]
            )
        result = self._build_result(
            effective_req_id, effective_conv_id, "completed",
            intent=intent.intent.value, response_type=response_type,
            trace=trace, trace_id=trace_id, is_mock=False,
            source_mode=self._source_mode, collector=collector,
            answer_text=answer_text,
            report_data=report_data,
            presentation=presentation,
            execution_audit={
                **semantic_audit,
                "canonical_query_plan": query_plan.model_dump(mode="json"),
                "deterministic_dax": not self.powerbi.is_mock,
                "dax_fingerprint": hashlib.sha256(
                    dax_request.dax.encode("utf-8")
                ).hexdigest(),
                "layer3_pass": not self.powerbi.is_mock,
                "query_result_success": query_result.error is None,
                "result_id": query_result.result_id,
                "result_row_count": query_result.row_count,
                "source_mode": query_result.source_mode,
                "verified_fact_set_id": (
                    verified_facts.fact_set_id if verified_facts else None
                ),
                "verified_fact_count": (
                    len(verified_facts.facts) if verified_facts else 0
                ),
                "verified_fact_types": (
                    sorted({item.fact_type.value for item in verified_facts.facts})
                    if verified_facts else []
                ),
                "factual_validation_pass": verified_facts is not None,
                "llm_dax_call_count": sum(
                    item.task == "dax" for item in collector.observations
                ),
                "memory_version": committed_memory.memory_version,
            },
        )
        return result

    async def _execute_sales_report_turn(
        self,
        *,
        message: str,
        memory: StructuredWorkMemory,
        intent: IntentSpec,
        schema: SemanticModelSchema,
        template_key: str,
        effective_req_id: str,
        effective_conv_id: str,
        runtime_mode: RuntimeDataMode,
        controller: TurnController,
        trace: TraceRecorder,
        trace_id: str,
        collector: LLMCallCollector,
    ) -> dict[str, Any]:
        """Execute the adaptive M3.4 sales report inside the active TurnPipeline.

        Flow: bounded report-intent weak signal → deterministic ReportPlanner
        (requested ∩ schema capability) → resolved query requirements →
        sealed M2 chain (plan → DAX → Layer 3 → Power BI → facts) →
        adaptive assembly → policy-driven ReportSpec → design-system renderer.
        """
        request_user_context = UserContext(
            allowed_semantic_models=[schema.key],
            allowed_templates=list(DEFAULT_TEMPLATE_CATALOG.allowed_keys),
        )
        request_validator = ValidationService(
            allowed_semantic_models=[schema.key],
            allowed_templates=DEFAULT_TEMPLATE_CATALOG.allowed_keys,
        )
        report_contract_validator = ReportContractValidator(
            binding_scope_key=self.settings.powerbi_local_semantic_model_key,
        )
        report_data_plan_builder = ReportDataPlanBuilder(
            validator=report_contract_validator,
        )
        report_planner = ReportPlanner(
            validator=report_contract_validator,
            data_plan_builder=report_data_plan_builder,
        )

        # ── 1. Bounded report-intent weak signal (LLM, registry IDs only) ──
        # Any failure fails closed to an empty draft; the deterministic
        # matcher below is always the floor.  The call is observed and
        # counted separately as llm_report_intent_call_count.
        llm_report_intent_ids: tuple[str, ...] = ()
        if not self.powerbi.is_mock:
            observed_report_intent = ObservedLLMProvider(
                self.llm_provider, collector
            )
            llm_report_intent_ids = await DeepSeekReportIntentService(
                observed_report_intent,
                max_format_repairs=0,
            ).draft(message)
        signal = resolve_report_intent(message, llm_draft=llm_report_intent_ids)
        trace.record(
            "report_intent_resolved",
            trace_id=trace_id,
            request_id=effective_req_id,
            data_summary={
                "llm_used": signal.llm_used,
                "scope_limited": signal.scope_limited,
                "requested_sections": list(signal.requested_ids),
                "llm_draft_ids": list(signal.llm_draft_ids),
            },
        )

        # ── 2. Deterministic ReportPlan (capability resolution) ──
        try:
            report_plan = report_planner.plan(
                template_key,
                schema,
                signal.requested_ids,
                signal,
                max_queries=self.settings.max_tool_calls - 2,
            )
        except ReportPlanError as exc:
            return await self._fail_result(
                memory,
                effective_req_id,
                effective_conv_id,
                controller,
                trace,
                terminal_state=TurnState.VALIDATION_FAILED,
                error_type=exc.code,
                reason=":".join((exc.code, *exc.errors)),
                stage="report_plan",
                trace_id=trace_id,
                collector=collector,
            )

        dax_requests: dict[str, DAXRequest] = {}
        try:
            for query in report_plan.data_plan.queries:
                plan_validation = request_validator.validate_query_plan(
                    query.query_plan,
                    schema,
                    enforce_semantic_grounding=True,
                )
                if not plan_validation.is_valid:
                    raise SalesReportAssemblyError(
                        "sales_report_query_plan_validation_failed"
                    )
                request = DeterministicDAXBuilder().build(
                    query.query_plan,
                    schema,
                    request_id=(
                        f"{effective_req_id}:report:{query.requirement_key}"
                    ),
                    timeout_seconds=self.settings.powerbi_query_timeout_seconds,
                )
                safety = DAXSafetyValidator().validate(request.dax, schema)
                if not safety.is_valid:
                    raise SalesReportAssemblyError(
                        "sales_report_dax_safety_failed"
                    )
                layer3 = request_validator.validate_dax_query_plan_consistency(
                    request,
                    query.query_plan,
                    schema,
                )
                if not layer3.is_valid:
                    raise SalesReportAssemblyError(
                        "sales_report_independent_layer3_failed"
                    )
                dax_requests[query.requirement_key] = request
        except (DAXBuildError, SalesReportAssemblyError) as exc:
            return await self._fail_result(
                memory,
                effective_req_id,
                effective_conv_id,
                controller,
                trace,
                terminal_state=TurnState.VALIDATION_FAILED,
                error_type=getattr(exc, "code", type(exc).__name__),
                reason=str(exc),
                stage="report_query_validation",
                trace_id=trace_id,
                collector=collector,
            )

        controller.record_query_plan_valid()
        controller.record_dax_valid()
        controller.transition(TurnState.QUERY_VALIDATED)
        trace.record(
            "report_data_plan_validated",
            trace_id=trace_id,
            request_id=effective_req_id,
            data_summary={
                "template_key": report_plan.template_key,
                "query_count": len(report_plan.data_plan.queries),
                "resolved_sections": [
                    item.value for item in report_plan.resolved_sections
                ],
                "unavailable_sections": [
                    item.value for item in report_plan.unavailable_sections
                ],
                "schema_fingerprint": report_plan.schema_fingerprint,
            },
        )

        exec_ctx = self.pipeline.create_tool_context(
            trace_id=trace_id,
            request_id=effective_req_id,
            conversation_id=effective_conv_id,
            runtime_mode=runtime_mode,
            intent=intent.intent,
            user=request_user_context,
        )
        query_results: dict[str, QueryResult] = {}
        try:
            for query in report_plan.data_plan.queries:
                result: QueryResult = await self.tool_gateway.execute(
                    TOOL_NAME_DAX,
                    exec_ctx,
                    dax_requests[query.requirement_key],
                    trace=trace,
                    controller=controller,
                )
                if result.error is not None:
                    return await self._fail_result(
                        memory,
                        effective_req_id,
                        effective_conv_id,
                        controller,
                        trace,
                        terminal_state=TurnState.TOOL_FAILED,
                        error_type=result.error.type,
                        reason=result.error.type,
                        stage="report_dax_execution",
                        trace_id=trace_id,
                        collector=collector,
                    )
                query_results[query.requirement_key] = result
        except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as exc:
            return await self._fail_result(
                memory,
                effective_req_id,
                effective_conv_id,
                controller,
                trace,
                terminal_state=TurnState.TOOL_FAILED,
                error_type=type(exc).__name__,
                reason=str(exc),
                stage="report_dax_execution",
                trace_id=trace_id,
                collector=collector,
            )

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)
        fact_sets: dict[str, VerifiedFactSet] = {}
        try:
            for query in report_plan.data_plan.queries:
                result = query_results[query.requirement_key]
                result_validation = request_validator.validate_query_result(
                    result,
                    expected_source_mode=self._source_mode,
                )
                if not result_validation.is_valid:
                    raise SalesReportAssemblyError(
                        "sales_report_query_result_validation_failed"
                    )
                fact_sets[query.requirement_key] = VerifiedFactSetBuilder().build(
                    query.query_plan,
                    result,
                )

            # ── 3. Fact-level re-gate: sections whose requirements returned
            # no verified rows are dropped (never rendered empty). ──
            fact_row_counts = {
                key: facts.row_count for key, facts in fact_sets.items()
            }
            still, dropped = report_planner.apply_fact_evidence(
                report_plan, schema, fact_row_counts
            )
            if not still:
                raise SalesReportAssemblyError(
                    "sales_report_no_resolved_sections"
                )
            remaining_keys: list[str] = []
            for section in (*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER):
                if section not in still:
                    continue
                for key in SECTION_REQUIREMENTS[section]:
                    if key not in remaining_keys:
                        remaining_keys.append(key)
            execution_plan = report_data_plan_builder.build(
                template_key,
                schema,
                requirement_keys=tuple(remaining_keys),
            )
            filtered_results = {
                query.requirement_key: query_results[query.requirement_key]
                for query in execution_plan.queries
            }
            filtered_facts = {
                requirement_key: fact_sets[requirement_key]
                for requirement_key in filtered_results
            }
            report_data_contract = SalesReportDataAssembler().build(
                execution_plan,
                filtered_results,
                filtered_facts,
            )
        except (FactVerificationError, SalesReportAssemblyError, ReportContractError) as exc:
            return await self._fail_result(
                memory,
                effective_req_id,
                effective_conv_id,
                controller,
                trace,
                terminal_state=TurnState.VALIDATION_FAILED,
                error_type=getattr(exc, "code", type(exc).__name__),
                reason=str(exc),
                stage="sales_report_data_assembly",
                trace_id=trace_id,
                collector=collector,
            )

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)
        trace.record(
            "sales_report_data_assembled",
            trace_id=trace_id,
            request_id=effective_req_id,
            data_summary={
                "query_result_ids": list(report_data_contract.query_result_ids),
                "verified_fact_set_ids": list(
                    report_data_contract.verified_fact_set_ids
                ),
                "source_mode": report_data_contract.source_mode,
                "dropped_sections": [item.value for item in dropped],
            },
        )

        try:
            report_spec = SalesReportSpecBuilder().build(report_data_contract)
            report_spec_with_ctx = report_spec.model_copy(update={
                "conversation_id": effective_conv_id,
                "request_id": effective_req_id,
            })
            rendered: ReportArtifact = await self.tool_gateway.execute(
                TOOL_NAME_RENDER,
                exec_ctx,
                report_spec_with_ctx,
                trace=trace,
                controller=controller,
            )
        except SalesReportAssemblyError as exc:
            return await self._fail_result(
                memory,
                effective_req_id,
                effective_conv_id,
                controller,
                trace,
                terminal_state=TurnState.RESPONSE_FAILED,
                error_type=exc.code,
                reason=exc.code,
                stage="sales_report_spec",
                trace_id=trace_id,
                collector=collector,
            )
        except (ToolTimeoutError, ToolExecutionError, ToolPolicyDeniedError,
                ToolNotRegisteredError, ToolOutputValidationError) as exc:
            return await self._fail_result(
                memory,
                effective_req_id,
                effective_conv_id,
                controller,
                trace,
                terminal_state=TurnState.RESPONSE_FAILED,
                error_type=type(exc).__name__,
                reason=str(exc),
                stage="report_render_store",
                trace_id=trace_id,
                collector=collector,
            )

        report_response = {
            "report_id": rendered.report_id,
            "template_key": rendered.template_key,
            "contract_version": rendered.contract_version,
            "view_reference": rendered.view_reference,
            "download_reference": rendered.download_reference,
            "content_type": rendered.content_type,
            "content_hash": rendered.content_hash,
            # Compatibility only: exact same bytes as the repository artifact.
            "html": rendered.html,
        }
        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)

        memory.current_intent = intent.intent.value
        memory.analysis_goal = f"用户提问: {message}"
        memory.semantic_model_key = report_plan.data_plan.semantic_model_key
        memory.report_template_key = report_plan.template_key
        # An adaptive multi-query report must not masquerade as one
        # inheritable user QueryPlan in the existing M2 memory slots.
        memory.measures = []
        memory.dimensions = []
        memory.filters = []
        memory.time_range = None
        memory.sort = None
        memory.top_n = None
        memory.comparison_mode = None
        memory.last_query_plan = None
        memory.last_dax = None
        memory.last_query_result_id = rendered.query_result_ids[-1]
        memory.last_result_summary = "adaptive sales report queries complete"
        memory.last_report_id = rendered.report_id
        memory.updated_at = datetime.utcnow()

        evidence = controller.build_commit_evidence()
        committed_memory, commit_error = await self.pipeline.commit_memory_safe(
            memory,
            evidence,
            controller,
            trace,
            trace_id,
            effective_req_id,
            runtime_mode,
        )
        if commit_error is not None:
            terminal_state = (
                "memory_conflict"
                if commit_error == "version_conflict"
                else "response_failed"
            )
            return self._build_result(
                effective_req_id,
                effective_conv_id,
                terminal_state,
                intent=intent.intent.value,
                error_type=commit_error,
                trace=trace,
                trace_id=trace_id,
                is_mock=False,
                source_mode=self._source_mode,
                collector=collector,
            )

        controller.transition(TurnState.COMPLETED)
        trace.record(
            "request_completed",
            trace_id=trace_id,
            request_id=effective_req_id,
            data_summary={"terminal_state": "completed"},
        )
        return self._build_result(
            effective_req_id,
            effective_conv_id,
            "completed",
            intent=intent.intent.value,
            response_type="report",
            trace=trace,
            trace_id=trace_id,
            is_mock=False,
            source_mode=self._source_mode,
            collector=collector,
            report_data=report_response,
            presentation=StructuredPresentationBuilder.build_report(
                report_response["report_id"]
            ),
            execution_audit={
                "canonical_query_plans": {
                    item.requirement_key: item.query_plan.model_dump(mode="json")
                    for item in report_plan.data_plan.queries
                },
                "requested_sections": list(signal.requested_ids),
                "resolved_sections": [
                    item.value for item in report_plan.resolved_sections
                ],
                "unavailable_sections": [
                    item.value for item in report_plan.unavailable_sections
                ],
                "query_count": len(report_plan.data_plan.queries),
                "assembled_query_count": len(execution_plan.queries),
                "deterministic_dax": True,
                "dax_fingerprints": {
                    key: hashlib.sha256(request.dax.encode("utf-8")).hexdigest()
                    for key, request in dax_requests.items()
                },
                "layer3_pass": True,
                "query_result_ids": list(rendered.query_result_ids),
                "verified_fact_set_ids": list(rendered.verified_fact_set_ids),
                "source_mode": rendered.source_mode,
                "factual_validation_pass": True,
                "llm_report_intent_call_count": sum(
                    item.task == LLMTask.REPORT_INTENT.value
                    for item in collector.observations
                ),
                "llm_dax_call_count": sum(
                    item.task == "dax" for item in collector.observations
                ),
                "llm_report_data_call_count": 0,
                "llm_report_factual_call_count": 0,
                "renderer_llm_call_count": 0,
                "fallback_count": 0,
                "fake_query_result_count": 0,
                "report_artifact_id": rendered.report_id,
                "content_hash": rendered.content_hash,
                "html_size_bytes": len(rendered.html.encode("utf-8")),
                "memory_version": committed_memory.memory_version,
            },
        )

    # ── 辅助方法：结果构建委托给共享 TurnPipeline ──

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
        # M1.6.3.2: Memory 失败标记统一通过 TurnPipeline
        await self.pipeline.mark_memory_failed(
            request_id, runtime_mode, reason=reason, stage=stage
        )

        trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                    error_type=error_type,
                    data_summary={"reason": reason, "stage": stage})

        return self._build_result(
            request_id, conversation_id, terminal_state.value,
            intent=memory.current_intent or "",
            error_type=error_type,
            trace=trace, trace_id=trace_id, is_mock=False,
            source_mode=self._source_mode, collector=collector,
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
        source_mode: Optional[str] = None,
        collector: Optional[LLMCallCollector] = None,
        answer_text: Optional[str] = None,
        report_data: Optional[dict[str, Any]] = None,
        clarification_question: Optional[str] = None,
        unsupported_reason: Optional[str] = None,
        execution_audit: Optional[dict[str, Any]] = None,
        presentation: Optional[PresentationEnvelope] = None,
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
            source_mode=source_mode or self._source_mode,
            allowed_tools=self.tool_gateway.list_tools(),
            answer_text=answer_text,
            report_data=report_data,
            clarification_question=clarification_question,
            unsupported_reason=unsupported_reason,
            usage=usage,
            execution_audit=execution_audit,
            presentation=presentation,
        )

    # M1.6.3.2: _build_replay 和 _save_snapshot 已移除 — 统一由 TurnPipeline.execute() 管理
