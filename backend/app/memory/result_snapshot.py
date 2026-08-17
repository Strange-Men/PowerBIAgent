"""TurnResultSnapshot — 最终响应快照，支持幂等重放

M1.0 新增：
- TurnResultSnapshot: 覆盖 Answer/Report/clarification/unsupported/失败 五类响应的 Pydantic 模型
- ResultSnapshotStore: 简单的内存快照存储，与 Repository 解耦

M1.0.1 修复：
- ReportResultSnapshot: Report 快照使用明确 Pydantic 模型，不再使用无约束 dict
- request_fingerprint_hash: 快照中保存请求指纹 Hash，支持冲突检测
- IdempotencyTracker: Owner/Waiter 并发防重机制（claim/complete/abort）
- 跨字段校验：response_type 与对应数据一致性

设计原则：
- 最终响应快照使用明确的 Pydantic 模型，不使用 dict[str, Any]
- 第一次请求保存快照，重复 request_id 返回完整快照
- 快照与 Memory 独立存储，不修改 StructuredWorkMemory 结构
- 同 request_id 不同指纹立即冲突，不同等
"""

import asyncio
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ReportResultSnapshot(BaseModel):
    """Report 响应快照 — M1.0.1

    替代旧的无约束 Optional[dict]，提供明确的 Pydantic 契约。
    """

    report_id: str = Field(min_length=1, description="报表唯一 ID")
    template_key: str = Field(min_length=1, description="报表模板标识")
    html: str = Field(min_length=1, description="渲染后的 HTML")
    contract_version: str = ""
    view_reference: str = ""
    download_reference: str = ""
    content_type: str = "text/html; charset=utf-8"
    content_hash: str = ""

    model_config = {"frozen": True}


class TurnResultSnapshot(BaseModel):
    """最终响应快照 — 覆盖所有终端状态

    用途：
    - 幂等重放：相同 request_id 相同指纹再次提交时返回完整快照
    - 冲突检测：相同 request_id 不同指纹时抛出 IdempotencyConflictError
    - 不依赖 Memory 是否存在（clarification/unsupported 无 Memory）
    - 使用明确 Pydantic 类型替代无约束 dict[str, Any]
    """

    request_id: str = Field(min_length=1, description="请求唯一标识")
    conversation_id: str = Field(min_length=1, description="会话 ID")
    intent: str = Field(default="", description="意图类型")
    response_type: str = Field(default="", description="answer / report / clarification / unsupported")
    terminal_state: str = Field(min_length=1, description="终端状态")

    # ── Answer 响应 ──
    answer: Optional[str] = Field(default=None, description="数据问答答案文本")

    # ── Report 响应 ── M1.0.1: 使用结构化模型
    report: Optional[ReportResultSnapshot] = Field(default=None, description="报表结构化数据")

    # ── clarification 响应 ──
    clarification_question: Optional[str] = Field(default=None, description="澄清问题")

    # ── unsupported 响应 ──
    unsupported_reason: Optional[str] = Field(default=None, description="拒绝原因")

    # ── 失败响应 ──
    error_type: Optional[str] = Field(default=None, description="错误类型")

    # ── 元数据 ──
    tool_sequence: list[str] = Field(default_factory=list, description="工具调用序列")
    memory_commit: bool = Field(default=False, description="是否提交了 Memory")
    final_memory_version: Optional[int] = Field(default=None, description="提交后的 memory_version")
    is_mock: bool = Field(default=True)
    source_mode: str = Field(
        default="mock",
        pattern="^(mock|real)$",
        description="数据来源；旧快照缺失时向后兼容为 mock",
    )
    trace_id: str = Field(default="")
    allowed_tools: list[str] = Field(default_factory=list)

    # ── M1.0.1: 请求指纹 Hash ──
    request_fingerprint_hash: str = Field(
        default="",
        description="请求指纹 SHA-256 Hash，用于冲突检测",
    )

    @model_validator(mode="after")
    def _validate_response_data(self) -> "TurnResultSnapshot":
        """跨字段校验：response_type 与对应数据一致性"""
        if self.response_type == "report":
            if self.report is None:
                raise ValueError("response_type='report' 时 report 不能为空")
        elif self.response_type == "answer":
            if self.answer is None:
                raise ValueError("response_type='answer' 时 answer 不能为空")
        elif self.response_type == "clarification":
            if self.clarification_question is None:
                raise ValueError("response_type='clarification' 时 clarification_question 不能为空")
        elif self.response_type == "unsupported":
            if self.unsupported_reason is None:
                raise ValueError("response_type='unsupported' 时 unsupported_reason 不能为空")
        return self


class IdempotencyClaimStatus(str, Enum):
    """幂等领取状态"""
    OWNER = "owner"        # 获得执行权，负责实际执行
    WAITER = "waiter"      # 等待 Owner 完成
    CONFLICT = "conflict"  # 指纹冲突，不可执行


class _InFlightEntry:
    """in-flight 追踪条目"""

    def __init__(self, fingerprint_hash: str):
        self.fingerprint_hash = fingerprint_hash
        self.waiters: list[asyncio.Future] = []


class IdempotencyTracker:
    """幂等执行追踪器 — M1.0.1 新增

    保证同一进程内相同 request_id 只有一个请求实际执行。
    使用 asyncio.Lock 保护 in-flight 字典。
    锁只用于领取执行权，不覆盖 LLM/工具执行过程。

    Service 实例之间不共享全局 in-flight 状态。
    不新增模块级可变全局变量。
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._in_flight: dict[tuple, _InFlightEntry] = {}

    def _key(self, request_id: str, runtime_mode) -> tuple:
        return (runtime_mode, request_id)

    async def claim(
        self,
        request_id: str,
        runtime_mode,
        fingerprint_hash: str,
    ) -> tuple[IdempotencyClaimStatus, Optional[asyncio.Future]]:
        """尝试领取执行权

        Returns:
            (status, future):
            - OWNER: future=None，调用方负责执行
            - WAITER: future=等待 Owner 完成的 Future
            - CONFLICT: future=None，调用方应抛出 IdempotencyConflictError
        """
        key = self._key(request_id, runtime_mode)
        async with self._lock:
            if key in self._in_flight:
                entry = self._in_flight[key]
                if entry.fingerprint_hash == fingerprint_hash:
                    # 相同指纹 → 等待 Owner
                    loop = asyncio.get_event_loop()
                    future = loop.create_future()
                    entry.waiters.append(future)
                    return IdempotencyClaimStatus.WAITER, future
                else:
                    # 不同指纹 → 冲突
                    return IdempotencyClaimStatus.CONFLICT, None
            else:
                # 首次领取 → Owner
                self._in_flight[key] = _InFlightEntry(fingerprint_hash=fingerprint_hash)
                return IdempotencyClaimStatus.OWNER, None

    async def complete(self, request_id: str, runtime_mode) -> None:
        """Owner 完成执行，唤醒所有 Waiter

        Owner 在保存快照后调用，确保 Waiter 可以从快照重放。
        """
        key = self._key(request_id, runtime_mode)
        async with self._lock:
            entry = self._in_flight.pop(key, None)
        if entry is not None:
            for future in entry.waiters:
                if not future.done():
                    future.set_result(True)

    async def abort(self, request_id: str, runtime_mode) -> None:
        """Owner 异常终止，清理 in-flight 状态并唤醒所有 Waiter

        Waiter 唤醒后发现无快照可重放，应重新尝试 claim。
        """
        from backend.app.memory.request_fingerprint import OwnerFailedError

        key = self._key(request_id, runtime_mode)
        async with self._lock:
            entry = self._in_flight.pop(key, None)
        if entry is not None:
            for future in entry.waiters:
                if not future.done():
                    future.set_exception(OwnerFailedError(
                        f"Owner for request_id '{request_id}' failed"
                    ))


class ResultSnapshotStore:
    """请求结果快照存储 — M1.0 新增

    职责：
    - 按 (runtime_mode, request_id) 复合键存储和检索 TurnResultSnapshot
    - M1.0.1: 集成 IdempotencyTracker 实现并发防重
    - 与 MemoryRepository 解耦，不修改 StructuredWorkMemory 结构
    - Mock 和 Real 模式快照隔离

    限制（文档说明）：
    - 当前为进程内存实现，重启后丢失
    - 跨进程持久化和分布式锁延后处理
    """

    def __init__(self):
        self._snapshots: dict[tuple, TurnResultSnapshot] = {}
        self._idempotency = IdempotencyTracker()

    def _key(self, request_id: str, runtime_mode) -> tuple:
        return (runtime_mode, request_id)

    # ── 快照存储 ──

    async def save(self, snapshot: TurnResultSnapshot, runtime_mode) -> None:
        """保存快照 — 相同键覆盖（幂等保存）"""
        key = self._key(snapshot.request_id, runtime_mode)
        self._snapshots[key] = snapshot

    async def get(
        self, request_id: str, runtime_mode
    ) -> Optional[TurnResultSnapshot]:
        """按 request_id + runtime_mode 获取快照"""
        key = self._key(request_id, runtime_mode)
        return self._snapshots.get(key)

    async def exists(self, request_id: str, runtime_mode) -> bool:
        """检查快照是否存在"""
        key = self._key(request_id, runtime_mode)
        return key in self._snapshots

    def _count(self) -> int:
        """获取快照总数（测试用）"""
        return len(self._snapshots)

    # ── M1.0.1: 并发防重 ──

    async def claim(
        self,
        request_id: str,
        runtime_mode,
        fingerprint_hash: str,
    ) -> tuple[IdempotencyClaimStatus, Optional[asyncio.Future]]:
        """尝试领取执行权

        Returns:
            (status, future):
            - OWNER: 获得执行权
            - WAITER: 需等待 Owner 完成，future 用于等待
            - CONFLICT: 指纹冲突，应拒绝
        """
        return await self._idempotency.claim(
            request_id, runtime_mode, fingerprint_hash
        )

    async def complete(self, request_id: str, runtime_mode) -> None:
        """Owner 完成执行，唤醒所有 Waiter"""
        await self._idempotency.complete(request_id, runtime_mode)

    async def abort(self, request_id: str, runtime_mode) -> None:
        """Owner 异常终止，清理并唤醒 Waiter"""
        await self._idempotency.abort(request_id, runtime_mode)
