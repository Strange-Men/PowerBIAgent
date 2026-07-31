"""记忆系统数据仓库接口

本轮 (M0.2) 定义数据契约和接口。SQLite 持久化在 M0.3 或 M1 实现。
"""

from abc import ABC, abstractmethod
from typing import Optional

from backend.app.memory.models import StructuredWorkMemory


class MemoryRepository(ABC):
    """记忆仓库抽象接口

    管理结构化工作记忆的 CRUD 和版本控制。
    """

    @abstractmethod
    async def get(self, request_id: str) -> Optional[StructuredWorkMemory]:
        """根据 request_id 获取记忆"""
        ...

    @abstractmethod
    async def get_latest_committed(self, conversation_id: str) -> Optional[StructuredWorkMemory]:
        """获取会话最新 committed 记忆"""
        ...

    @abstractmethod
    async def save(self, memory: StructuredWorkMemory) -> None:
        """保存记忆（含乐观锁检查）

        Raises:
            MemoryVersionConflictError: memory_version 冲突
        """
        ...

    @abstractmethod
    async def list_by_conversation(
        self, conversation_id: str, status: Optional[str] = None, limit: int = 20
    ) -> list[StructuredWorkMemory]:
        """列出会话记忆"""
        ...

    @abstractmethod
    async def delete_request_id(self, request_id: str) -> bool:
        """幂等删除：按 request_id 删除（用于重复请求处理）"""
        ...


class MemoryVersionConflictError(Exception):
    """乐观锁冲突异常"""
    pass


class MemoryCommitDeniedError(Exception):
    """记忆提交被拒绝（未满足完整成功边界）"""
    pass
