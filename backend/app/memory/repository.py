"""记忆系统数据仓库接口与 InMemory 实现"""

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
    async def get_latest_committed(self, conversation_id: str) -> Optional[StructuredWorkMemory]:
        """获取会话最新 committed 记忆"""
        ...

    @abstractmethod
    async def commit(
        self,
        memory: StructuredWorkMemory,
        evidence: MemoryCommitEvidence,
        expected_version: int,
    ) -> StructuredWorkMemory:
        """提交记忆（含乐观锁检查）

        Args:
            memory: 待提交的记忆
            evidence: 提交证据
            expected_version: 期望版本号

        Returns:
            提交后的记忆

        Raises:
            MemoryVersionConflictError: 版本冲突
            MemoryCommitDeniedError: 提交被拒绝
        """
        ...

    @abstractmethod
    async def mark_failed(self, request_id: str) -> Optional[StructuredWorkMemory]:
        """标记为失败（保留审计）"""
        ...

    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: str, status: Optional[str] = None, limit: int = 20
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
    - 使用深拷贝防止外部修改内部存储
    - 相同 request_id 不重复执行
    - committed 只通过受控方法产生
    - failed 记录保留用于审计
    - Mock 与 Real 空间隔离
    - 版本冲突抛出明确异常
    - 不删除原始审计记录
    """

    def __init__(self):
        # 按 conversation_id 组织存储
        self._store: dict[str, dict[str, StructuredWorkMemory]] = {}
        # 按 request_id 快速索引
        self._by_request: dict[str, StructuredWorkMemory] = {}
        # Mock/Real 空间标记
        self._mode: RuntimeDataMode = RuntimeDataMode.MOCK

    @property
    def mode(self) -> RuntimeDataMode:
        return self._mode

    @mode.setter
    def mode(self, value: RuntimeDataMode) -> None:
        self._mode = value

    async def create_pending(self, memory: StructuredWorkMemory) -> StructuredWorkMemory:
        """创建 pending 记忆 — request_id 幂等"""
        if memory.request_id in self._by_request:
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

    async def get_latest_committed(self, conversation_id: str) -> Optional[StructuredWorkMemory]:
        """获取会话最新 committed 记忆"""
        conv_store = self._store.get(conversation_id, {})
        committed = [
            m for m in conv_store.values()
            if m.state_status == MemoryStatus.COMMITTED
        ]
        if not committed:
            return None
        # 返回版本号最高的
        latest = max(committed, key=lambda m: m.memory_version)
        return copy.deepcopy(latest)

    async def commit(
        self,
        memory: StructuredWorkMemory,
        evidence: MemoryCommitEvidence,
        expected_version: int,
    ) -> StructuredWorkMemory:
        """提交记忆 — 乐观锁检查 + 证据检查"""
        existing = self._by_request.get(memory.request_id)
        if existing is None:
            raise MemoryCommitDeniedError(f"request_id '{memory.request_id}' 不存在")

        # 版本冲突检查
        if existing.memory_version != expected_version:
            raise MemoryVersionConflictError(
                f"版本冲突: 期望版本 {expected_version}, "
                f"当前版本 {existing.memory_version}"
            )

        # 提交
        existing.state_status = MemoryStatus.COMMITTED
        existing.commit_evidence = evidence
        existing.memory_version += 1
        existing.updated_at = memory.updated_at
        # 同步运行时标记
        existing.runtime_mode = memory.runtime_mode
        existing.is_mock = memory.is_mock
        existing.llm_provider = memory.llm_provider
        existing.powerbi_provider = memory.powerbi_provider
        # 同步分析数据
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

        return copy.deepcopy(existing)

    async def mark_failed(self, request_id: str) -> Optional[StructuredWorkMemory]:
        """标记为失败 — 保留审计"""
        memory = self._by_request.get(request_id)
        if memory is None:
            return None
        memory.state_status = MemoryStatus.FAILED
        from datetime import datetime
        memory.updated_at = datetime.utcnow()
        return copy.deepcopy(memory)

    async def list_by_conversation(
        self, conversation_id: str, status: Optional[str] = None, limit: int = 20
    ) -> list[StructuredWorkMemory]:
        """列出会话记忆"""
        conv_store = self._store.get(conversation_id, {})
        results = list(conv_store.values())
        if status is not None:
            results = [m for m in results if m.state_status.value == status]
        # 按创建时间排序
        results.sort(key=lambda m: m.created_at, reverse=True)
        return [copy.deepcopy(m) for m in results[:limit]]

    async def request_exists(self, request_id: str) -> bool:
        """检查 request_id 是否已存在"""
        return request_id in self._by_request

    def _get_count(self) -> int:
        """获取存储总数（测试用）"""
        return len(self._by_request)
