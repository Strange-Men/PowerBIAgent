"""TurnPipeline — M1.6.3 共享确定性执行骨架

Mock 和 DeepSeek 路径共享同一执行骨架，两者只在以下部分不同：
- LLM 阶段实现（Intent、QueryPlan、DAX、Answer/ReportSpec）
- Provider
- Adapter 或 Fixture

共享骨架统一以下职责：
- ID 生成（request_id、conversation_id、trace_id）
- 请求指纹
- Owner/Waiter 幂等协调
- TraceRecorder 创建
- TurnController 创建与生命周期管理
- ContextBuilder 统一入口
- ToolExecutionContext 工厂
- 通用 Memory 失败标记
- Snapshot 保存、重放与 abort

每个 do_execute 回调只管 LLM 结构化阶段，不复制通用控制面。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Optional

from backend.app.harness.models import HarnessConfig
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.runtime.context_builder import ContextBuilder
from backend.app.harness.runtime.tool_gateway import ToolExecutionContext
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.memory.models import (
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
)
from backend.app.memory.result_snapshot import (
    IdempotencyClaimStatus,
    ReportResultSnapshot,
    ResultSnapshotStore,
    TurnResultSnapshot,
)
from backend.app.schemas.data_contracts import UserContext


# _do_execute 回调签名
# 接收执行上下文，返回结果 dict
DoExecuteCallback = Callable[..., Any]


class TurnPipeline:
    """共享确定性 TurnPipeline 执行骨架

    MockTurnService 和 DeepSeekTurnService 各持有一个 TurnPipeline 实例。
    TurnPipeline 负责执行骨架（ID、指纹、幂等、Snapshot、TurnController、
    ContextBuilder、通用失败处理），具体 LLM 管线通过 _do_execute 回调注入。
    """

    def __init__(
        self,
        config: HarnessConfig,
        memory_repo: InMemoryMemoryRepository,
        snapshot_store: Optional[ResultSnapshotStore] = None,
    ):
        self.config = config
        self.memory_repo = memory_repo
        self.snapshot_store = snapshot_store or ResultSnapshotStore()
        self.context_builder = ContextBuilder(config)

    async def execute(
        self,
        *,
        message: str,
        conversation_id: Optional[str],
        request_id: Optional[str],
        semantic_model_key: str,
        report_template_key: Optional[str],
        runtime_mode: RuntimeDataMode,
        is_mock: bool,
        llm_provider_name: str,
        powerbi_provider_name: str,
        scenario_fingerprint_hash_inputs: Optional[dict[str, Any]] = None,
        do_execute: DoExecuteCallback,
        **execute_kwargs: Any,
    ) -> dict[str, Any]:
        """共享 execute 骨架

        1. 统一 ID 生成
        2. 请求指纹计算
        3. 幂等快照检查
        4. Owner/Waiter 并发协调
        5. 委托 do_execute 回调执行 LLM 管线
        6. Snapshot 完成/异常中止
        """

        # ── 统一 ID 生成 ──
        effective_conv_id = conversation_id or str(uuid.uuid4())
        effective_req_id = request_id or str(uuid.uuid4())

        # ── 请求指纹 ──
        fingerprint_inputs: dict[str, Any] = {
            "message": message,
            "client_conversation_id": conversation_id,
            "semantic_model_key": semantic_model_key,
            "effective_report_template_key": report_template_key,
        }
        if scenario_fingerprint_hash_inputs:
            fingerprint_inputs.update(scenario_fingerprint_hash_inputs)

        fingerprint_hash = RequestFingerprint.compute_hash(**fingerprint_inputs)

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

        # ── OWNER: 执行前准备（统一控制面） ──
        # 加载 committed memory
        committed = await self.memory_repo.get_latest_committed(
            effective_conv_id, runtime_mode
        )

        # 构建上下文
        context = self.context_builder.build(
            user_message=message,
            committed_memory=committed,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
        )
        trace.record("context_built", trace_id=trace_id, request_id=effective_req_id)

        # 创建 TurnController
        controller = TurnController(self.config, request_id=effective_req_id)
        controller.transition(TurnState.CONTEXT_READY)

        # ── OWNER: 执行 LLM 管线 ──
        try:
            result = await do_execute(
                message=message,
                effective_conv_id=effective_conv_id,
                effective_req_id=effective_req_id,
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
                runtime_mode=runtime_mode,
                is_mock=is_mock,
                llm_provider_name=llm_provider_name,
                powerbi_provider_name=powerbi_provider_name,
                trace=trace,
                trace_id=trace_id,
                fingerprint_hash=fingerprint_hash,
                controller=controller,
                context=context,
                committed=committed,
                **execute_kwargs,
            )
            await self._save_snapshot(result, runtime_mode, fingerprint_hash)
            await self.snapshot_store.complete(effective_req_id, runtime_mode)
            return result
        except Exception:
            await self.snapshot_store.abort(effective_req_id, runtime_mode)
            raise

    # ── 共享辅助方法 ──

    def build_result(
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
        allowed_tools: Optional[list[str]] = None,
        answer_text: Optional[str] = None,
        report_data: Optional[dict[str, Any]] = None,
        clarification_question: Optional[str] = None,
        unsupported_reason: Optional[str] = None,
        usage: Optional[Any] = None,
    ) -> dict[str, Any]:
        """构建统一结果字典"""

        tool_sequence: list[str] = []
        if trace is not None:
            tool_sequence = trace.get_tool_sequence()

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
            "allowed_tools": allowed_tools or [],
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

    def build_replay(
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
            "final_memory_version": snapshot.final_memory_version,
            "trace_id": trace_id,
            "is_mock": snapshot.is_mock,
            "source_mode": snapshot.source_mode,
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
            final_memory_version=result.get("final_memory_version"),
            is_mock=result.get("is_mock", False),
            source_mode=result.get("source_mode", "mock"),
            trace_id=result.get("trace_id", ""),
            allowed_tools=result.get("allowed_tools", []),
            request_fingerprint_hash=fingerprint_hash,
        )
        await self.snapshot_store.save(snapshot, runtime_mode)

    # ── 共享控制面方法 ──

    def create_tool_context(
        self,
        trace_id: str,
        request_id: str,
        conversation_id: str,
        runtime_mode: RuntimeDataMode,
        intent: Any,
        user: Optional[UserContext] = None,
    ) -> ToolExecutionContext:
        """统一 ToolExecutionContext 工厂"""
        return ToolExecutionContext(
            trace_id=trace_id,
            request_id=request_id,
            conversation_id=conversation_id,
            runtime_mode=runtime_mode,
            intent=intent,
            user=user or UserContext(),
        )

    async def create_pending_memory(
        self,
        conversation_id: str,
        request_id: str,
        semantic_model_key: str,
        report_template_key: Optional[str],
        intent_value: str,
        runtime_mode: RuntimeDataMode,
        is_mock: bool,
        llm_provider_name: str,
        powerbi_provider_name: str,
        base_version: int,
    ) -> StructuredWorkMemory:
        """统一创建 pending memory"""
        memory = StructuredWorkMemory(
            conversation_id=conversation_id,
            request_id=request_id,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            current_intent=intent_value,
            state_status=MemoryStatus.PENDING,
            runtime_mode=runtime_mode,
            is_mock=is_mock,
            llm_provider=llm_provider_name,
            powerbi_provider=powerbi_provider_name,
            base_memory_version=base_version,
            memory_version=0,
        )
        await self.memory_repo.create_pending(memory, runtime_mode)
        return memory

    async def mark_memory_failed(
        self,
        request_id: str,
        runtime_mode: RuntimeDataMode,
        reason: str,
        stage: str,
    ) -> None:
        """统一 Memory 失败标记（静默吞掉异常，因为已经处于失败路径）"""
        try:
            await self.memory_repo.mark_failed(
                request_id, runtime_mode, reason=reason, stage=stage
            )
        except Exception:
            pass

    async def commit_memory(
        self,
        memory: StructuredWorkMemory,
        evidence: Any,
    ) -> StructuredWorkMemory:
        """统一 Memory 原子提交"""
        return await self.memory_repo.commit(memory, evidence)

    async def commit_memory_safe(
        self,
        memory: StructuredWorkMemory,
        evidence: Any,
        controller: TurnController,
        trace: TraceRecorder,
        trace_id: str,
        request_id: str,
        runtime_mode: RuntimeDataMode,
    ) -> tuple[Optional[StructuredWorkMemory], Optional[str]]:
        """安全 Memory 提交 — 返回 (committed_memory, error_type_or_None)"""
        try:
            committed_memory = await self.memory_repo.commit(memory, evidence)
            controller.record_version_matches()
            controller.transition(TurnState.MEMORY_COMMITTED)
            trace.record("memory_committed", trace_id=trace_id, request_id=request_id,
                        data_summary={"version": committed_memory.memory_version})
            return committed_memory, None
        except MemoryVersionConflictError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.MEMORY_CONFLICT)
            await self.mark_memory_failed(
                request_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            return None, "version_conflict"
        except MemoryCommitDeniedError as e:
            controller.set_failure_reason(str(e))
            controller.transition(TurnState.RESPONSE_FAILED)
            await self.mark_memory_failed(
                request_id, runtime_mode, reason=str(e), stage="memory_commit"
            )
            return None, "memory_commit_denied"

    def fail_controller_safe(
        self,
        controller: TurnController,
        terminal_state: TurnState,
        reason: str,
        trace: TraceRecorder,
        trace_id: str,
        request_id: str,
    ) -> None:
        """安全设置 controller 失败状态"""
        controller.set_failure_reason(reason)
        try:
            controller.transition(terminal_state)
        except Exception:
            pass
        trace.record("request_failed", trace_id=trace_id, request_id=request_id,
                    error_type="turn_failed",
                    data_summary={"reason": reason})

    # ── 只读 Memory 查询（Service 不得直接持有 memory_repo 写入能力） ──

    async def get_latest_committed_memory(
        self, conversation_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[StructuredWorkMemory]:
        """只读查询：按 conversation_id 获取最近 committed Memory

        用于测试验证和Service只读查询。
        这是只读操作，不涉及任何写入。
        """
        return await self.memory_repo.get_latest_committed(conversation_id, runtime_mode)

    async def request_exists_in_memory(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> bool:
        """只读检查：request_id 是否已存在于 Memory 中

        MockTurnService 的快照缺失向后兼容回退使用。
        这是只读操作，不涉及任何写入。
        """
        return await self.memory_repo.request_exists(request_id, runtime_mode)

    async def get_memory_by_request_id(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[StructuredWorkMemory]:
        """只读查询：按 request_id 获取 Memory 记录

        MockTurnService 的快照缺失向后兼容回退使用。
        这是只读操作，不涉及任何写入。
        """
        return await self.memory_repo.get_by_request_id(request_id, runtime_mode)

    # Backward-compatible aliases (used by existing services during migration)
    _build_result = build_result
    _build_replay = build_replay
