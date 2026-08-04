"""MockTurnService — 确定性应用服务（非 FastAPI 接口）

M0.3.2 修复：
- 工具序列唯一来源：TraceRecorder.get_tool_sequence()，不再手工拼装
- Schema 失败路径合法状态转换
- 统一 _fail_turn 处理所有失败分支
- ToolExecutionContext 传入 Gateway
- Gateway 集成 TraceRecorder
- last_query_result_id/last_report_id 使用唯一 result_id/report_id
- Memory 冲突时 pending 标记 failed、不返回 memory_commit=True

M1.0 修复：
- _build_result() 接收 conversation_id 参数，clarification/unsupported 不再返回空 conversation_id
- request_id 幂等重放：第一次保存 TurnResultSnapshot，重复请求返回完整快照
- MockScenarioResolver 返回 MockScenarioResolution（含 effective_report_template_key）
- 默认报表模板固定为 sales_weekly，贯穿 Memory/API 全链路

M1.0.1 修复：
- Service 未传 conversation_id/request_id 时生成 UUID
- 请求指纹与冲突检测：相同 request_id 不同指纹 → IdempotencyConflictError
- 并发 Owner/Waiter 防重：相同指纹等待，不同指纹冲突
- Report 快照使用 ReportResultSnapshot Pydantic 模型
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
from backend.app.harness.models import HarnessConfig
from backend.app.harness.tool_registry import SchemaInput, create_default_tool_gateway
from backend.app.harness.runtime.context_builder import ContextBuilder
from backend.app.harness.runtime.tool_gateway import (
    ToolExecutionContext,
    ToolGateway,
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
from backend.app.memory.request_fingerprint import (
    IdempotencyConflictError,
    IdempotencyCoordinationError,
    OwnerFailedError,
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
        self.config = config or HarnessConfig()

        self.context_builder = ContextBuilder(self.config)
        self.tool_gateway = self._build_tool_gateway()
        self.validator = ValidationService()
        # M1.0: 快照存储 — 支持幂等重放
        # M1.0.1: 集成 IdempotencyTracker 并发防重
        self.snapshot_store = ResultSnapshotStore()

    def _build_tool_gateway(self) -> ToolGateway:
        """构建 ToolGateway — M1.6.2 使用共享工具注册入口，超时/重试来自 HarnessConfig"""
        return create_default_tool_gateway(self.powerbi, self.report_renderer, self.config)

    async def execute(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
        scenario: Optional[MockScenarioSelection] = None,
        intent_key: Optional[str] = None,
        powerbi_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 Turn 流程

        M1.0.1:
        - conversation_id 和 request_id 未传时服务端生成 UUID
        - 请求指纹检测相同 request_id 不同内容冲突
        - Owner/Waiter 并发防重

        scenario=None 时使用 MockScenarioResolver 自动推断（API 路径）。
        显式传入 scenario 仅用于 Golden Cases 和内部测试。
        intent_key/powerbi_key 为向后兼容保留。
        """
        # ── M1.0.1: 统一生成 ID ──
        effective_conv_id = conversation_id or str(uuid.uuid4())
        effective_req_id = request_id or str(uuid.uuid4())

        # ── M1.0: 构建 Scenario 与 effective_report_template_key ──
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

        runtime_mode = RuntimeDataMode.MOCK if self.config.is_mock else RuntimeDataMode.REAL

        # ── M1.1: 将 MockScenarioSelection 转换为 Memory 层 ScenarioFingerprint ──
        scenario_fp: Optional[ScenarioFingerprint] = None
        if resolved_scenario is not None:
            scenario_fp = ScenarioFingerprint(
                intent_key=resolved_scenario.intent_key,
                query_plan_key=resolved_scenario.query_plan_key,
                dax_key=resolved_scenario.dax_key,
                powerbi_key=resolved_scenario.powerbi_key,
                response_key=resolved_scenario.response_key,
            )

        # ── M1.0.1: 计算请求指纹 ──
        fingerprint_hash = RequestFingerprint.compute_hash(
            message=message,
            client_conversation_id=conversation_id,  # 原始客户端值，可能为 None
            semantic_model_key=semantic_model_key,
            effective_report_template_key=effective_template_key,
            scenario=scenario_fp,
            intent_key=intent_key,
            powerbi_key=powerbi_key,
        )

        trace_id = str(uuid.uuid4())
        trace = TraceRecorder(self.config)

        # ── M1.0.1: 检查已完成快照（含指纹对比） ──
        snapshot = await self.snapshot_store.get(effective_req_id, runtime_mode)
        if snapshot is not None:
            if snapshot.request_fingerprint_hash != fingerprint_hash:
                raise IdempotencyConflictError(
                    request_id=effective_req_id,
                    detail="request_id has already been used by a different request",
                )
            # 指纹一致 → 幂等重放
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "duplicate"})
            return self._build_idempotent_replay(
                snapshot, effective_req_id, trace_id,
            )

        # ── M1.0.1: Owner/Waiter 并发防重 ──
        # 最多重试 3 次（处理 Owner 异常终止场景）
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
                # 等待 Owner 完成
                try:
                    await claim_future
                except OwnerFailedError:
                    # Owner 异常终止 → 重试 claim
                    continue

                # Owner 正常完成 → 从快照重放
                snapshot = await self.snapshot_store.get(effective_req_id, runtime_mode)
                if snapshot is not None:
                    new_trace_id = str(uuid.uuid4())
                    return self._build_idempotent_replay(
                        snapshot, effective_req_id, new_trace_id,
                    )
                # 快照不存在（极端情况）→ 重试
                continue

            elif claim_status == IdempotencyClaimStatus.OWNER:
                # 获得执行权
                break
        else:
            # 重试耗尽 → 协调失败 (HTTP 503)
            raise IdempotencyCoordinationError(
                request_id=effective_req_id,
                detail="Unable to acquire execution right after retries",
            )

        # ── OWNER: 执行完整流程 ──
        try:
            result = await self._do_execute(
                message=message,
                effective_conv_id=effective_conv_id,
                effective_req_id=effective_req_id,
                semantic_model_key=semantic_model_key,
                effective_template_key=effective_template_key,
                resolved_scenario=resolved_scenario,
                runtime_mode=runtime_mode,
                trace=trace,
                trace_id=trace_id,
            )
            # 保存快照（含指纹 Hash）
            await self._save_snapshot(
                result, runtime_mode, fingerprint_hash
            )
            # 唤醒 Waiter
            await self.snapshot_store.complete(effective_req_id, runtime_mode)
            return result
        except Exception:
            # Owner 异常 → 清理 in-flight 状态并唤醒 Waiter
            await self.snapshot_store.abort(effective_req_id, runtime_mode)
            raise

    async def _do_execute(
        self,
        message: str,
        effective_conv_id: str,
        effective_req_id: str,
        semantic_model_key: str,
        effective_template_key: Optional[str],
        resolved_scenario: MockScenarioSelection,
        runtime_mode: RuntimeDataMode,
        trace: TraceRecorder,
        trace_id: str,
    ) -> dict[str, Any]:
        """Owner 执行完整 Turn 流程（原 execute 的核心逻辑）"""

        trace.record("request_received", trace_id=trace_id, request_id=effective_req_id,
                     conversation_id=effective_conv_id)

        # fallback: Memory 中存在但快照缺失（向后兼容）
        if await self.memory_repo.request_exists(effective_req_id, runtime_mode):
            existing = await self.memory_repo.get_by_request_id(effective_req_id, runtime_mode)
            trace.record("request_completed", trace_id=trace_id, request_id=effective_req_id,
                        data_summary={"terminal_state": "duplicate"})
            return self._build_result(
                existing, effective_req_id, "duplicate", trace_id=trace_id,
                trace=trace, conversation_id=effective_conv_id,
            )

        # 2. 加载最新 committed memory
        committed = await self.memory_repo.get_latest_committed(
            effective_conv_id, runtime_mode
        )

        # 3. 构建上下文
        context = self.context_builder.build(
            user_message=message,
            committed_memory=committed,
            semantic_model_key=semantic_model_key,
            report_template_key=effective_template_key,
        )
        trace.record("context_built", trace_id=trace_id, request_id=effective_req_id)

        # 4. 意图识别 — M0.3.3: scenario_key 通过 context 局部传递
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

        # 6. 创建 pending memory
        base_version = committed.memory_version if committed is not None else 0
        memory = StructuredWorkMemory(
            conversation_id=effective_conv_id,
            request_id=effective_req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=effective_template_key,
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
        controller = TurnController(self.config, request_id=effective_req_id)
        controller.transition(TurnState.CONTEXT_READY)
        controller.transition(TurnState.INTENT_CLASSIFIED)
        controller.record_intent_valid()

        # 8. 生成 QueryPlan
        context["mock_scenario_key"] = resolved_scenario.query_plan_key
        plan_result = await self.llm.run(message, context, QueryPlan)
        query_plan: QueryPlan = plan_result.structured  # type: ignore[assignment]
        trace.record("plan_created", trace_id=trace_id, request_id=effective_req_id)

        # 9. 通过 ToolGateway 获取 Schema
        controller.transition(TurnState.PLAN_READY)
        try:
            exec_ctx = ToolExecutionContext(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=UserContext(),
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
            await self.memory_repo.mark_failed(
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

        # 11. 生成 DAX
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
            await self.memory_repo.mark_failed(
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
            exec_ctx = ToolExecutionContext(
                trace_id=trace_id,
                request_id=effective_req_id,
                conversation_id=effective_conv_id,
                runtime_mode=runtime_mode,
                intent=intent.intent,
                user=UserContext(),
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
            await self.memory_repo.mark_failed(
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
            await self.memory_repo.mark_failed(
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
                await self.memory_repo.mark_failed(
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

            report_validation = self.validator.validate_report(report_spec, schema, query_result)
            if not report_validation.is_valid:
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                await self.memory_repo.mark_failed(
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
                exec_ctx = ToolExecutionContext(
                    trace_id=trace_id,
                    request_id=effective_req_id,
                    conversation_id=effective_conv_id,
                    runtime_mode=runtime_mode,
                    intent=intent.intent,
                    user=UserContext(),
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

        # 16. 原子提交
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
            trace.record("memory_commit_rejected", trace_id=trace_id, request_id=effective_req_id,
                        error_type="version_conflict")
            return self._build_result(
                memory, effective_req_id, "memory_conflict", intent=intent.intent.value,
                error_type="version_conflict", trace_id=trace_id,
                trace=trace,
                conversation_id=effective_conv_id,
            )
        except MemoryCommitDeniedError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.RESPONSE_FAILED)
            await self.memory_repo.mark_failed(
                effective_req_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            return self._build_result(
                memory, effective_req_id, "response_failed", intent=intent.intent.value,
                error_type="memory_commit_denied", trace_id=trace_id,
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
        """统一失败处理"""

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

    def _build_idempotent_replay(
        self,
        snapshot: "TurnResultSnapshot",
        request_id: str,
        trace_id: str,
    ) -> dict[str, Any]:
        """M1.0: 构建幂等重放响应，M1.0.1: Report 使用结构化模型"""

        # M1.0.1: Report 从 ReportResultSnapshot 转回 dict（兼容现有 API）
        report_dict: Optional[dict[str, Any]] = None
        if snapshot.report is not None:
            report_dict = {
                "report_id": snapshot.report.report_id,
                "template_key": snapshot.report.template_key,
                "html": snapshot.report.html,
            }

        result: dict[str, Any] = {
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
            "final_memory_version": snapshot.final_memory_version,
            "is_mock": snapshot.is_mock,
            "trace_id": trace_id,
            "allowed_tools": snapshot.allowed_tools,
            "idempotent_replay": True,
            "replayed_request_id": snapshot.request_id,
        }
        return result

    async def _save_snapshot(
        self,
        result: dict[str, Any],
        runtime_mode: RuntimeDataMode,
        fingerprint_hash: str,
    ) -> None:
        """M1.0.1: 从 _build_result 输出构建并保存 TurnResultSnapshot（含指纹 Hash）"""

        # M1.0.1: Report 转换为 ReportResultSnapshot
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
            final_memory_version=result.get("final_memory_version"),
            is_mock=result.get("is_mock", True),
            trace_id=result.get("trace_id", ""),
            allowed_tools=result.get("allowed_tools", []),
            request_fingerprint_hash=fingerprint_hash,
        )
        await self.snapshot_store.save(snapshot, runtime_mode)
