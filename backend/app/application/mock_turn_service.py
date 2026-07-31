"""MockTurnService — 确定性应用服务（非 FastAPI 接口）

完整流程：接收请求 → 加载记忆 → 构建上下文 → 意图识别 →
生成 QueryPlan → 获取 Schema → 验证 → DAX → 工具执行 →
验证结果 → 生成 Answer/Report → 提交 Memory → 返回结果

由普通、明确、可测试的 Python 流程控制。
不引入 LangGraph。
不让 LLM 决定事务、状态提交或权限。
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from backend.app.agent.mock_runtime import MockAgentRuntime
from backend.app.harness.models import DEFAULT_MOCK_CONFIG, HarnessConfig
from backend.app.harness.runtime.context_builder import ContextBuilder
from backend.app.harness.runtime.tool_gateway import ToolGateway, ToolSpec
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import LLMTask
from backend.app.memory.models import MemoryCommitEvidence, MemoryStatus
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
    ReportSpec,
    SemanticModelSchema,
    UserContext,
)


class MockTurnService:
    """Mock 轮次服务

    完整的确定性流程控制，不使用 LLM 做编排决策。
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
        self.tool_gateway = ToolGateway()
        self.validator = ValidationService()
        self._trace: Optional[TraceRecorder] = None

    async def execute(
        self,
        message: str,
        conversation_id: str = "test-conv",
        request_id: Optional[str] = None,
        semantic_model_key: str = "mock_sales_model",
        report_template_key: Optional[str] = None,
        initial_memory: Optional[dict[str, Any]] = None,
        intent_key: Optional[str] = None,
        powerbi_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行完整 Turn 流程"""
        req_id = request_id or str(uuid.uuid4())
        trace = TraceRecorder(self.config)
        self._trace = trace

        trace.record("request_received", request_id=req_id, conversation_id=conversation_id)

        # 1. 检查 request_id 幂等
        if await self.memory_repo.request_exists(req_id):
            existing = await self.memory_repo.get_by_request_id(req_id)
            return self._build_result(existing, req_id, "duplicate")

        # 2. 加载最新 committed memory
        committed = await self.memory_repo.get_latest_committed(conversation_id)

        # 3. 创建 pending turn
        from backend.app.memory.models import StructuredWorkMemory
        memory = StructuredWorkMemory(
            conversation_id=conversation_id,
            request_id=req_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            state_status=MemoryStatus.PENDING,
            runtime_mode="mock",
            is_mock=True,
            llm_provider="mock",
            powerbi_provider="mock_powerbi",
        )
        if initial_memory:
            for k, v in initial_memory.items():
                if hasattr(memory, k):
                    setattr(memory, k, v)

        await self.memory_repo.create_pending(memory)

        # 4. TurnController
        controller = TurnController(self.config, request_id=req_id)
        controller.transition(TurnState.CONTEXT_READY)

        # 5. ContextBuilder
        context = self.context_builder.build(
            user_message=message,
            committed_memory=committed,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
        )
        trace.record("context_built", request_id=req_id)

        # 6. 意图识别
        self.llm.set_scenario(intent_key or "data_question")
        intent_result = await self.llm.run(
            message, context, IntentSpec
        )
        intent: IntentSpec = intent_result.structured  # type: ignore[assignment]
        trace.record("intent_classified", request_id=req_id,
                     data_summary={"intent": intent.intent.value})

        controller.record_intent_valid()
        controller.transition(TurnState.INTENT_CLASSIFIED)

        # 7. clarification/unsupported → 终止
        if intent.intent == IntentType.CLARIFICATION:
            controller.transition(TurnState.CLARIFICATION_REQUIRED)
            memory.clarification_pending = True
            memory.clarification_question = intent.clarification_question
            trace.record("request_completed", request_id=req_id,
                        data_summary={"terminal_state": "clarification_required"})
            return self._build_result(memory, req_id, "clarification_required",
                                     intent=intent.intent.value)

        if intent.intent == IntentType.UNSUPPORTED:
            controller.transition(TurnState.UNSUPPORTED)
            trace.record("request_completed", request_id=req_id,
                        data_summary={"terminal_state": "unsupported"})
            return self._build_result(memory, req_id, "unsupported",
                                     intent=intent.intent.value)

        # 8. 生成 QueryPlan
        self.llm.set_scenario(intent_key or "data_question")
        plan_result = await self.llm.run(message, context, QueryPlan)
        query_plan: QueryPlan = plan_result.structured  # type: ignore[assignment]
        trace.record("plan_created", request_id=req_id)

        # 9. 获取 Schema
        schema = await self.powerbi.get_semantic_model_schema(semantic_model_key)
        controller.transition(TurnState.PLAN_READY)

        # 10. 验证 QueryPlan
        plan_validation = self.validator.validate_query_plan(query_plan, schema)
        if not plan_validation.is_valid:
            controller.set_failure_reason(str(plan_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            trace.record("request_failed", request_id=req_id,
                        data_summary={"reason": str(plan_validation.errors)})
            return self._build_result(memory, req_id, "validation_failed",
                                     error_type="validation_failed")

        controller.record_query_plan_valid()
        controller.transition(TurnState.QUERY_VALIDATED)

        # 11. 生成 DAX
        self.llm.set_scenario(intent_key or "data_question")
        dax_result = await self.llm.run(message, context, DAXRequest)
        dax_req: DAXRequest = dax_result.structured  # type: ignore[assignment]
        dax_req.semantic_model_key = semantic_model_key
        dax_req.request_id = powerbi_key or intent_key or "data_question"
        dax_req.is_mock = True

        dax_validation = self.validator.validate_dax(dax_req)
        if not dax_validation.is_valid:
            controller.set_failure_reason(str(dax_validation.errors))
            controller.transition(TurnState.VALIDATION_FAILED)
            return self._build_result(memory, req_id, "validation_failed",
                                     error_type="dax_validation_failed")

        controller.record_dax_valid()

        # 12. 执行 Power BI 查询
        controller.check_tool_call_limit()
        try:
            query_result = await self.powerbi.execute_dax(dax_req)
        except Exception as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.TOOL_FAILED)
            trace.record("tool_call_failed", request_id=req_id, error_type="tool_failed")
            await self.memory_repo.mark_failed(req_id)
            return self._build_result(memory, req_id, "tool_failed", error_type="tool_failed")

        controller.record_tool_execution_succeeded()
        controller.transition(TurnState.TOOL_EXECUTED)
        trace.record("tool_call_completed", request_id=req_id,
                     data_summary={"row_count": query_result.row_count})

        # 13. 验证 QueryResult
        result_validation = self.validator.validate_query_result(query_result)
        if query_result.error is not None:
            controller.set_failure_reason(query_result.error.message)
            controller.transition(TurnState.TOOL_FAILED)
            await self.memory_repo.mark_failed(req_id)
            return self._build_result(memory, req_id, "tool_failed",
                                     error_type=query_result.error.type)

        controller.record_query_result_valid()
        controller.transition(TurnState.RESULT_VALIDATED)

        # 14. 生成回答或报表
        if intent.intent == IntentType.DATA_QUESTION:
            self.llm.set_scenario(intent_key or "data_question")
            answer_result = await self.llm.run(message, context, AnswerSpec)
            response_obj: AnswerSpec = answer_result.structured  # type: ignore[assignment]
            response_type = "answer"
        else:
            self.llm.set_scenario("report_generation")
            report_result = await self.llm.run(message, context, ReportSpec)
            report_spec: ReportSpec = report_result.structured  # type: ignore[assignment]

            # 验证 ReportSpec
            report_validation = self.validator.validate_report(report_spec, schema)
            if not report_validation.is_valid:
                controller.set_failure_reason(str(report_validation.errors))
                controller.transition(TurnState.RESPONSE_FAILED)
                return self._build_result(memory, req_id, "response_failed",
                                         error_type="report_validation_failed")

            # render_report
            try:
                html = await self.report_renderer.render(report_spec)
            except ValueError as e:
                controller.set_failure_reason(str(e))
                controller.transition(TurnState.RESPONSE_FAILED)
                return self._build_result(memory, req_id, "response_failed",
                                         error_type="report_render_failed")

            response_obj = report_spec
            response_type = "report"

        controller.record_response_valid()
        controller.transition(TurnState.RESPONSE_READY)

        # 15. Memory Commit
        evidence = controller.build_commit_evidence()
        try:
            committed_memory = await self.memory_repo.commit(
                memory, evidence, memory.memory_version
            )
            controller.record_version_matches()
            controller.transition(TurnState.MEMORY_COMMITTED)
            trace.record("memory_committed", request_id=req_id,
                        data_summary={"version": committed_memory.memory_version})
        except MemoryVersionConflictError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.MEMORY_CONFLICT)
            return self._build_result(memory, req_id, "memory_conflict", error_type="version_conflict")

        controller.transition(TurnState.COMPLETED)
        trace.record("request_completed", request_id=req_id)

        # 更新 memory 中的分析数据
        committed_memory.current_intent = intent.intent.value
        committed_memory.measures = query_plan.measures
        committed_memory.dimensions = query_plan.dimensions
        committed_memory.last_dax = dax_req.dax
        committed_memory.last_result_summary = f"{query_result.row_count} rows"

        return self._build_result(
            committed_memory, req_id, "completed",
            intent=intent.intent.value,
            response_type=response_type,
            tool_sequence=["get_semantic_model_schema", "execute_dax"],
            state_changes={"memory_version": committed_memory.memory_version},
        )

    def _build_result(
        self,
        memory: Any,
        request_id: str,
        terminal_state: str,
        intent: str = "",
        response_type: str = "",
        error_type: Optional[str] = None,
        tool_sequence: Optional[list[str]] = None,
        state_changes: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """构建统一结果字典"""
        return {
            "request_id": request_id,
            "conversation_id": getattr(memory, "conversation_id", ""),
            "terminal_state": terminal_state,
            "intent": intent,
            "response_type": response_type,
            "error_type": error_type,
            "tool_sequence": tool_sequence or [],
            "state_changes": state_changes or {},
            "memory_commit": terminal_state == "completed",
            "final_memory_version": getattr(memory, "memory_version", None),
            "inherited_context": getattr(memory, "last_result_summary", None),
            "allowed_tools": ["get_semantic_model_schema", "execute_dax", "render_report"],
            "is_mock": True,
        }
