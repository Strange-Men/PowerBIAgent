"""TurnResultSnapshot — 最终响应快照，支持幂等重放

M1.0 新增：
- TurnResultSnapshot: 覆盖 Answer/Report/clarification/unsupported/失败 五类响应的 Pydantic 模型
- ResultSnapshotStore: 简单的内存快照存储，与 Repository 解耦

设计原则：
- 最终响应快照使用明确的 Pydantic 模型，不使用 dict[str, Any]
- 第一次请求保存快照，重复 request_id 返回完整快照
- 快照与 Memory 独立存储，不修改 StructuredWorkMemory 结构
"""

from typing import Optional

from pydantic import BaseModel, Field

from backend.app.memory.models import RuntimeDataMode


class TurnResultSnapshot(BaseModel):
    """最终响应快照 — 覆盖所有终端状态

    用途：
    - 幂等重放：相同 request_id 再次提交时返回完整快照
    - 不依赖 Memory 是否存在（clarification/unsupported 无 Memory）
    - 使用明确 Pydantic 类型替代无约束 dict[str, Any]
    """

    request_id: str = Field(description="请求唯一标识")
    conversation_id: str = Field(description="会话 ID")
    intent: str = Field(default="", description="意图类型")
    response_type: str = Field(default="", description="answer / report / clarification / unsupported")
    terminal_state: str = Field(description="终端状态")

    # ── Answer 响应 ──
    answer: Optional[str] = Field(default=None, description="数据问答答案文本")

    # ── Report 响应 ──
    report: Optional[dict] = Field(default=None, description="报表结构化数据 {report_id, template_key, html}")

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
    trace_id: str = Field(default="")
    allowed_tools: list[str] = Field(default_factory=list)


class ResultSnapshotStore:
    """请求结果快照存储 — M1.0 新增

    职责单一：按 (runtime_mode, request_id) 复合键存储和检索 TurnResultSnapshot。
    与 MemoryRepository 解耦，不修改 StructuredWorkMemory 结构。
    Mock 和 Real 模式快照隔离。
    """

    def __init__(self):
        self._snapshots: dict[tuple, TurnResultSnapshot] = {}

    def _key(self, request_id: str, runtime_mode: RuntimeDataMode) -> tuple:
        return (runtime_mode, request_id)

    async def save(self, snapshot: TurnResultSnapshot, runtime_mode: RuntimeDataMode) -> None:
        """保存快照 — 相同键覆盖（幂等保存）"""
        key = self._key(snapshot.request_id, runtime_mode)
        self._snapshots[key] = snapshot

    async def get(
        self, request_id: str, runtime_mode: RuntimeDataMode
    ) -> Optional[TurnResultSnapshot]:
        """按 request_id + runtime_mode 获取快照"""
        key = self._key(request_id, runtime_mode)
        return self._snapshots.get(key)

    async def exists(self, request_id: str, runtime_mode: RuntimeDataMode) -> bool:
        """检查快照是否存在"""
        key = self._key(request_id, runtime_mode)
        return key in self._snapshots

    def _count(self) -> int:
        """获取快照总数（测试用）"""
        return len(self._snapshots)
