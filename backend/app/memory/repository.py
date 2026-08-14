"""记忆系统数据仓库接口与 InMemory 实现

M0.3.2 修复：
- request_id 索引使用 (runtime_mode, request_id) 复合键
- request_exists/get_by_request_id/mark_failed/create_pending 全部显式接收 runtime_mode
- Mock 和 Real 相同 request_id 可以共存
- 同模式重复 request_id 仍幂等拦截
"""

import asyncio
import copy
from abc import ABC, abstractmethod
from typing import Optional

from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    PendingClarificationContext,
    RuntimeDataMode,
    StructuredWorkMemory,
)


class MemoryRepository(ABC):
    """记忆仓库抽象接口"""

    @abstractmethod
    async def create_pending(
        self, memory: StructuredWorkMemory, runtime_mode: RuntimeDataMode
    ) -> StructuredWorkMemory:
        """创建 pending 记忆（request_id + runtime_mode 复合键幂等）

        Raises:
            MemoryDuplicateError: 同模式 request_id 已存在
        """
        ...

    @abstractmethod
    async def get_by_request_id(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[StructuredWorkMemory]:
        """按 request_id + runtime_mode 获取记忆"""
        ...

    @abstractmethod
    async def get_latest_committed(
        self, conversation_id: str, runtime_mode: Optional[RuntimeDataMode] = None
    ) -> Optional[StructuredWorkMemory]:
        """获取会话最新 committed 记忆（按 runtime_mode 过滤）"""
        ...

    @abstractmethod
    async def commit(
        self,
        memory: StructuredWorkMemory,
        evidence: MemoryCommitEvidence,
    ) -> StructuredWorkMemory:
        """提交记忆（含乐观锁检查与证据验证）"""
        ...

    @abstractmethod
    async def mark_failed(
        self, request_id: str, runtime_mode: RuntimeDataMode,
        reason: Optional[str] = None, stage: Optional[str] = None
    ) -> Optional[StructuredWorkMemory]:
        """标记为失败（保留审计）"""
        ...

    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: str, status: Optional[str] = None,
        runtime_mode: Optional[RuntimeDataMode] = None, limit: int = 20
    ) -> list[StructuredWorkMemory]:
        """列出会话记忆"""
        ...

    @abstractmethod
    async def request_exists(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> bool:
        """检查 request_id + runtime_mode 是否已存在"""
        ...

    @abstractmethod
    async def save_pending_clarification(
        self,
        context: PendingClarificationContext,
        runtime_mode: RuntimeDataMode,
    ) -> PendingClarificationContext:
        """Create or replace the non-committed clarification chain."""
        ...

    @abstractmethod
    async def get_pending_clarification(
        self, conversation_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[PendingClarificationContext]:
        """Read the active clarification chain for one mode-isolated conversation."""
        ...

    @abstractmethod
    async def clear_pending_clarification(
        self, conversation_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[PendingClarificationContext]:
        """Remove and return the active clarification chain, if any."""
        ...


class MemoryVersionConflictError(Exception):
    """乐观锁冲突异常"""
    pass


class MemoryCommitDeniedError(Exception):
    """记忆提交被拒绝（未满足完整成功边界）"""
    pass


class MemoryDuplicateError(Exception):
    """重复 request_id 异常"""
    pass


def _composite_key(request_id: str, runtime_mode: RuntimeDataMode) -> tuple:
    """生成复合键"""
    return (runtime_mode, request_id)


class InMemoryMemoryRepository(MemoryRepository):
    """基于内存字典的 MemoryRepository

    特性：
    - asyncio.Lock 保护 create_pending/commit/mark_failed 原子性
    - 版本检查和版本递增在同一个临界区完成
    - 使用深拷贝防止外部修改内部存储
    - request_id + runtime_mode 复合键索引
    - Mock 和 Real 相同 request_id 可以共存
    - 同模式重复 request_id 幂等拦截
    - committed 只通过受控方法产生
    - failed 记录保留用于审计
    - Mock 与 Real 空间严格隔离
    """

    def __init__(self):
        self._store: dict[str, dict[str, StructuredWorkMemory]] = {}
        # 复合键索引：(runtime_mode, request_id) → StructuredWorkMemory
        self._by_request: dict[tuple, StructuredWorkMemory] = {}
        self._pending_clarifications: dict[
            tuple[RuntimeDataMode, str], PendingClarificationContext
        ] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, request_id: str, runtime_mode: RuntimeDataMode) -> tuple:
        return _composite_key(request_id, runtime_mode)

    async def create_pending(
        self, memory: StructuredWorkMemory, runtime_mode: RuntimeDataMode
    ) -> StructuredWorkMemory:
        """创建 pending 记忆 — (request_id, runtime_mode) 复合键幂等"""
        async with self._lock:
            key = self._make_key(memory.request_id, runtime_mode)
            if key in self._by_request:
                existing = self._by_request[key]
                raise MemoryDuplicateError(
                    f"request_id '{memory.request_id}' 在 "
                    f"'{runtime_mode.value}' 模式已存在，不重复创建"
                )
            stored = copy.deepcopy(memory)
            stored.state_status = MemoryStatus.PENDING
            stored.runtime_mode = runtime_mode
            self._by_request[key] = stored
            conv = stored.conversation_id
            if conv not in self._store:
                self._store[conv] = {}
            self._store[conv][stored.request_id] = stored
            return copy.deepcopy(stored)

    async def get_by_request_id(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[StructuredWorkMemory]:
        """按 request_id + runtime_mode 获取记忆"""
        key = self._make_key(request_id, runtime_mode)
        memory = self._by_request.get(key)
        return copy.deepcopy(memory) if memory else None

    async def get_latest_committed(
        self, conversation_id: str, runtime_mode: Optional[RuntimeDataMode] = None
    ) -> Optional[StructuredWorkMemory]:
        """获取会话最新 committed 记忆（按 runtime_mode 过滤）"""
        conv_store = self._store.get(conversation_id, {})
        committed = [
            m for m in conv_store.values()
            if m.state_status == MemoryStatus.COMMITTED
        ]
        if runtime_mode is not None:
            committed = [m for m in committed if m.runtime_mode == runtime_mode]
        if not committed:
            return None
        latest = max(committed, key=lambda m: m.memory_version)
        return copy.deepcopy(latest)

    async def commit(
        self,
        memory: StructuredWorkMemory,
        evidence: MemoryCommitEvidence,
    ) -> StructuredWorkMemory:
        """提交记忆 — 原子版本检查 + 证据验证"""
        runtime_mode = memory.runtime_mode
        async with self._lock:
            key = self._make_key(memory.request_id, runtime_mode)
            existing = self._by_request.get(key)
            if existing is None:
                raise MemoryCommitDeniedError(
                    f"request_id '{memory.request_id}' 在 "
                    f"'{runtime_mode.value}' 模式不存在"
                )

            # 1. 状态检查
            if existing.state_status != MemoryStatus.PENDING:
                raise MemoryCommitDeniedError(
                    f"仅有 pending 状态可以提交，当前状态: {existing.state_status.value}"
                )
            if existing.state_status == MemoryStatus.FAILED:
                raise MemoryCommitDeniedError("failed 状态不可提交")

            # 2. 业务证据检查
            if evidence.failure_reason is not None and evidence.failure_reason != "":
                raise MemoryCommitDeniedError(
                    f"存在失败原因，不可提交: {evidence.failure_reason}"
                )

            if evidence.intent_valid is False:
                raise MemoryCommitDeniedError("意图无效，不可提交")

            if evidence.request_allowed is False:
                raise MemoryCommitDeniedError("请求未被允许，不可提交")

            if not evidence.business_satisfied:
                missing = []
                if not evidence.query_plan_valid: missing.append("query_plan_valid")
                if not evidence.dax_valid: missing.append("dax_valid")
                if not evidence.tool_execution_succeeded: missing.append("tool_execution_succeeded")
                if not evidence.query_result_valid: missing.append("query_result_valid")
                if not evidence.response_valid: missing.append("response_valid")
                raise MemoryCommitDeniedError(
                    f"业务证据不完整: {', '.join(missing)}"
                )

            # 3. 运行时模式一致性
            if memory.runtime_mode != existing.runtime_mode:
                raise MemoryCommitDeniedError(
                    f"运行时模式不一致: {memory.runtime_mode.value} vs {existing.runtime_mode.value}"
                )

            # 4. 版本冲突检查（原子）
            conv_store = self._store.get(existing.conversation_id, {})
            current_committed = [
                m for m in conv_store.values()
                if (m.state_status == MemoryStatus.COMMITTED
                    and m.runtime_mode == memory.runtime_mode
                    and m.request_id != memory.request_id)
            ]
            current_latest_version = 0
            if current_committed:
                current_latest_version = max(m.memory_version for m in current_committed)

            base_version = memory.base_memory_version
            if base_version != current_latest_version:
                raise MemoryVersionConflictError(
                    f"版本冲突: 期望 base 版本 {base_version}, "
                    f"当前会话最新 committed 版本 {current_latest_version}"
                )

            # 5. 同步完整分析数据
            existing.current_intent = memory.current_intent
            existing.analysis_goal = memory.analysis_goal
            existing.semantic_model_key = memory.semantic_model_key
            existing.report_template_key = memory.report_template_key
            existing.measures = copy.deepcopy(memory.measures)
            existing.dimensions = copy.deepcopy(memory.dimensions)
            existing.filters = copy.deepcopy(memory.filters)
            existing.time_range = memory.time_range
            existing.sort = memory.sort
            existing.top_n = memory.top_n
            existing.comparison_mode = memory.comparison_mode
            existing.last_query_plan = copy.deepcopy(memory.last_query_plan)
            existing.last_dax = memory.last_dax
            existing.last_query_result_id = memory.last_query_result_id
            existing.last_result_summary = memory.last_result_summary
            existing.last_report_id = memory.last_report_id
            existing.runtime_mode = memory.runtime_mode
            existing.is_mock = memory.is_mock
            existing.llm_provider = memory.llm_provider
            existing.powerbi_provider = memory.powerbi_provider
            existing.updated_at = memory.updated_at

            # 6. 原子提交 — 设置 version_matches + 递增版本
            evidence.version_matches = True
            existing._mark_committed(evidence)

            return copy.deepcopy(existing)

    async def mark_failed(
        self, request_id: str, runtime_mode: RuntimeDataMode,
        reason: Optional[str] = None, stage: Optional[str] = None
    ) -> Optional[StructuredWorkMemory]:
        """标记为失败 — 保留审计"""
        async with self._lock:
            key = self._make_key(request_id, runtime_mode)
            memory = self._by_request.get(key)
            if memory is None:
                return None
            memory._mark_failed(reason=reason, stage=stage)
            return copy.deepcopy(memory)

    async def list_by_conversation(
        self, conversation_id: str, status: Optional[str] = None,
        runtime_mode: Optional[RuntimeDataMode] = None, limit: int = 20
    ) -> list[StructuredWorkMemory]:
        """列出会话记忆（支持 runtime_mode 过滤）"""
        conv_store = self._store.get(conversation_id, {})
        results = list(conv_store.values())
        if status is not None:
            results = [m for m in results if m.state_status.value == status]
        if runtime_mode is not None:
            results = [m for m in results if m.runtime_mode == runtime_mode]
        results.sort(key=lambda m: m.created_at, reverse=True)
        return [copy.deepcopy(m) for m in results[:limit]]

    async def request_exists(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> bool:
        """检查 (request_id, runtime_mode) 复合键是否已存在"""
        key = self._make_key(request_id, runtime_mode)
        return key in self._by_request

    async def save_pending_clarification(
        self,
        context: PendingClarificationContext,
        runtime_mode: RuntimeDataMode,
    ) -> PendingClarificationContext:
        async with self._lock:
            stored = context.model_copy(
                deep=True, update={"runtime_mode": runtime_mode}
            )
            self._pending_clarifications[
                (runtime_mode, stored.conversation_id)
            ] = stored
            return stored.model_copy(deep=True)

    async def get_pending_clarification(
        self, conversation_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[PendingClarificationContext]:
        context = self._pending_clarifications.get((runtime_mode, conversation_id))
        return context.model_copy(deep=True) if context else None

    async def clear_pending_clarification(
        self, conversation_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[PendingClarificationContext]:
        async with self._lock:
            context = self._pending_clarifications.pop(
                (runtime_mode, conversation_id), None
            )
            return context.model_copy(deep=True) if context else None

    def _get_count(self) -> int:
        """获取存储总数（测试用）"""
        return len(self._by_request)
