"""记忆系统数据仓库接口与 InMemory 实现"""

import asyncio
import copy
from abc import ABC, abstractmethod
from typing import Optional

from backend.app.memory.models import (
    MemoryCommitEvidence,
    MemoryStatus,
    RuntimeDataMode,
    StructuredWorkMemory,
)


class MemoryRepository(ABC):
    """记忆仓库抽象接口

    M0.2 定义契约，M0.3 提供 InMemoryMemoryRepository。
    """

    @abstractmethod
    async def create_pending(self, memory: StructuredWorkMemory) -> StructuredWorkMemory:
        """创建 pending 记忆（request_id 幂等）

        Raises:
            MemoryDuplicateError: request_id 已存在
        """
        ...

    @abstractmethod
    async def get_by_request_id(self, request_id: str) -> Optional[StructuredWorkMemory]:
        """按 request_id 获取记忆"""
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
        """提交记忆（含乐观锁检查与证据验证）

        Args:
            memory: 待提交的记忆（必须包含完整分析字段）
            evidence: 提交证据（business 条件由 TurnController 产生，
                      version_matches 由 Repository 在原子提交阶段设置）

        Returns:
            提交后的记忆

        Raises:
            MemoryVersionConflictError: 版本冲突
            MemoryCommitDeniedError: 提交被拒绝
        """
        ...

    @abstractmethod
    async def mark_failed(
        self, request_id: str, reason: Optional[str] = None, stage: Optional[str] = None
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
    async def request_exists(self, request_id: str) -> bool:
        """检查 request_id 是否已存在"""
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


class InMemoryMemoryRepository(MemoryRepository):
    """基于内存字典的 MemoryRepository

    特性：
    - asyncio.Lock 保护 create_pending/commit/mark_failed 原子性
    - 版本检查和版本递增在同一个临界区完成
    - 使用深拷贝防止外部修改内部存储
    - 相同 request_id 不重复执行（按 runtime_mode 隔离）
    - committed 只通过受控方法产生
    - failed 记录保留用于审计
    - Mock 与 Real 空间严格隔离
    - 版本冲突抛出明确异常
    - 拒绝不完整 Evidence
    - 保存完整 Memory 快照
    - 不删除原始审计记录
    """

    def __init__(self):
        # 按 conversation_id 组织存储
        self._store: dict[str, dict[str, StructuredWorkMemory]] = {}
        # 按 request_id 快速索引
        self._by_request: dict[str, StructuredWorkMemory] = {}
        # 原子操作锁
        self._lock = asyncio.Lock()

    async def create_pending(self, memory: StructuredWorkMemory) -> StructuredWorkMemory:
        """创建 pending 记忆 — request_id 幂等"""
        async with self._lock:
            if memory.request_id in self._by_request:
                existing = self._by_request[memory.request_id]
                # 允许同一 runtime_mode 的幂等（返回已存在记录）
                # 不允许跨 runtime_mode 冲突
                if existing.runtime_mode != memory.runtime_mode:
                    raise MemoryDuplicateError(
                        f"request_id '{memory.request_id}' 已存在于 "
                        f"'{existing.runtime_mode.value}' 模式，"
                        f"不能在 '{memory.runtime_mode.value}' 模式重复创建"
                    )
                raise MemoryDuplicateError(
                    f"request_id '{memory.request_id}' 已存在，不重复创建"
                )
            stored = copy.deepcopy(memory)
            stored.state_status = MemoryStatus.PENDING
            self._by_request[stored.request_id] = stored
            conv = stored.conversation_id
            if conv not in self._store:
                self._store[conv] = {}
            self._store[conv][stored.request_id] = stored
            return copy.deepcopy(stored)

    async def get_by_request_id(self, request_id: str) -> Optional[StructuredWorkMemory]:
        """按 request_id 获取记忆"""
        memory = self._by_request.get(request_id)
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
        # 返回版本号最高的
        latest = max(committed, key=lambda m: m.memory_version)
        return copy.deepcopy(latest)

    async def commit(
        self,
        memory: StructuredWorkMemory,
        evidence: MemoryCommitEvidence,
    ) -> StructuredWorkMemory:
        """提交记忆 — 原子版本检查 + 证据验证

        版本语义：
        - base_memory_version 是开始本轮时读取到的版本
        - 提交时检查当前会话最新 committed 版本是否与 base 匹配
        - 匹配成功则 memory_version = base + 1
        - 版本检查和写入在同一个临界区完成
        """
        async with self._lock:
            existing = self._by_request.get(memory.request_id)
            if existing is None:
                raise MemoryCommitDeniedError(f"request_id '{memory.request_id}' 不存在")

            # 1. 状态检查
            if existing.state_status != MemoryStatus.PENDING:
                raise MemoryCommitDeniedError(
                    f"仅有 pending 状态可以提交，当前状态: {existing.state_status.value}"
                )
            if existing.state_status == MemoryStatus.FAILED:
                raise MemoryCommitDeniedError("failed 状态不可提交")

            # 2. 业务证据检查（逐项检查，给出明确失败原因）
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

            # 4. 版本冲突检查（原子：检查当前会话最新 committed 版本）
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

            # 5. 同步完整分析数据到 existing（Commit 前必须写完）
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
            existing.base_memory_version = existing.base_memory_version  # 保留原始 base
            existing.updated_at = memory.updated_at

            # 6. 原子提交：版本匹配成功 → 设置 version_matches 并递增版本
            evidence.version_matches = True
            existing._mark_committed(evidence)

            return copy.deepcopy(existing)

    async def mark_failed(
        self, request_id: str, reason: Optional[str] = None, stage: Optional[str] = None
    ) -> Optional[StructuredWorkMemory]:
        """标记为失败 — 保留审计"""
        async with self._lock:
            memory = self._by_request.get(request_id)
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
        # 按创建时间排序
        results.sort(key=lambda m: m.created_at, reverse=True)
        return [copy.deepcopy(m) for m in results[:limit]]

    async def request_exists(self, request_id: str) -> bool:
        """检查 request_id 是否已存在"""
        return request_id in self._by_request

    def _get_count(self) -> int:
        """获取存储总数（测试用）"""
        return len(self._by_request)
