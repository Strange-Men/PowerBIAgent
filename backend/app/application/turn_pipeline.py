"""TurnPipeline — M1.6.3 共享确定性执行骨架

Mock 和 DeepSeek 路径共享同一执行骨架，两者只在以下部分不同：
- LLM 阶段实现（Intent、QueryPlan、DAX、Answer/ReportSpec）
- Provider
- Adapter 或 Fixture

共享骨架统一以下职责：
- ID 生成（request_id、conversation_id、trace_id）
- 请求指纹
- Owner/Waiter 幂等协调
- TraceRecorder
- TurnController
- ContextBuilder
- ToolGateway
- 状态转换
- Memory 提交与失败处理
- Snapshot 保存与重放
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Optional

from backend.app.harness.models import HarnessConfig
from backend.app.harness.observability.trace_recorder import TraceRecorder
from backend.app.harness.runtime.turn_controller import TurnController, TurnState
from backend.app.memory.models import RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
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


# _do_execute 回调签名
# 接收执行上下文，返回结果 dict
DoExecuteCallback = Callable[..., Any]


class TurnPipeline:
    """共享确定性 TurnPipeline 执行骨架

    MockTurnService 和 DeepSeekTurnService 各持有一个 TurnPipeline 实例。
    TurnPipeline 负责执行骨架（ID、指纹、幂等、Snapshot），
    具体 LLM 管线通过 _do_execute 回调注入。
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

        # ── OWNER: 执行 ──
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
            final_memory_version=result.get("final_memory_version"),
            is_mock=result.get("is_mock", False),
            trace_id=result.get("trace_id", ""),
            allowed_tools=result.get("allowed_tools", []),
            request_fingerprint_hash=fingerprint_hash,
        )
        await self.snapshot_store.save(snapshot, runtime_mode)

    # Backward-compatible aliases (used by existing services during migration)
    _build_result = build_result
    _build_replay = build_replay
