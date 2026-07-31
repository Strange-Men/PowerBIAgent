"""记忆系统数据模型

固定三态：pending、committed、failed

只有满足完整成功边界时，才能提交 committed memory。
完整成功边界至少要求：
- 意图有效
- 请求未被拒绝
- 查询计划有效
- DAX 校验成功
- 工具执行成功
- 查询结果校验成功
- 最终回答或 ReportSpec 成功
- memory_version 未冲突
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MemoryStatus(str, Enum):
    """记忆状态三态机制"""

    PENDING = "pending"      # 轮次进行中，尚未达到完整成功边界
    COMMITTED = "committed"  # 轮次已完整成功，记忆已可靠提交
    FAILED = "failed"        # 轮次失败，记忆不提交


class StructuredWorkMemory(BaseModel):
    """结构化工作记忆

    当前轮次的分析上下文，包含指标、维度、时间、筛选等要素。
    只有 status == committed 的记忆才会在 Context Assembly 中加载。
    """

    # 会话标识
    conversation_id: str = Field(default_factory=lambda: str(uuid4()), description="会话 ID")
    request_id: str = Field(default_factory=lambda: str(uuid4()), description="请求唯一标识（幂等键）")

    # 语义模型和报表
    semantic_model_key: Optional[str] = Field(default=None, description="当前语义模型 Key")
    report_template_key: Optional[str] = Field(default=None, description="当前报表模板 Key")

    # 意图和分析目标
    current_intent: Optional[str] = Field(default=None, description="当前意图类型")
    analysis_goal: Optional[str] = Field(default=None, description="分析目标描述")

    # 分析要素
    measures: list[str] = Field(default_factory=list, description="指标列表")
    dimensions: list[str] = Field(default_factory=list, description="维度列表")
    filters: list[dict[str, str]] = Field(default_factory=list, description="筛选条件")
    time_range: Optional[str] = Field(default=None, description="时间范围")
    sort: Optional[str] = Field(default=None, description="排序方式")
    top_n: Optional[int] = Field(default=None, ge=1, description="Top N 限制")
    comparison_mode: Optional[str] = Field(default=None, description="对比模式")

    # 最近一次查询
    last_query_plan: Optional[dict] = Field(default=None, description="最近一次 QueryPlan")
    last_dax: Optional[str] = Field(default=None, description="最近一次 DAX")
    last_query_result_id: Optional[str] = Field(default=None, description="最近一次查询结果 ID")
    last_result_summary: Optional[str] = Field(default=None, description="最近一次查询结果摘要")
    last_report_id: Optional[str] = Field(default=None, description="最近一次报表 ID")

    # 澄清
    clarification_pending: bool = Field(default=False, description="是否有待澄清问题")
    clarification_question: Optional[str] = Field(default=None, description="待澄清问题文本")

    # 版本和状态
    memory_version: int = Field(default=1, ge=1, description="乐观锁版本号")
    state_status: MemoryStatus = Field(default=MemoryStatus.PENDING, description="记忆状态")

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="最后更新时间")

    # Mock 标记
    is_mock: bool = Field(default=False, description="是否由 Mock LLM 生成（不可标记为真实业务结果）")

    @field_validator("state_status")
    @classmethod
    def failed_status_cannot_be_committed(cls, v: MemoryStatus, info) -> MemoryStatus:
        """failed 状态不可作为 committed 状态"""
        return v

    def bump_version(self) -> None:
        """递增 memory_version"""
        self.memory_version += 1
        self.updated_at = datetime.utcnow()

    def commit(self) -> None:
        """标记为已提交（仅当满足完整成功边界时调用）"""
        if self.state_status == MemoryStatus.FAILED:
            raise ValueError("failed 状态的记忆不可标记为 committed")
        self.state_status = MemoryStatus.COMMITTED
        self.bump_version()

    def fail(self) -> None:
        """标记为失败"""
        self.state_status = MemoryStatus.FAILED
        self.updated_at = datetime.utcnow()

    def is_committable(self) -> bool:
        """检查是否满足提交条件"""
        return (
            self.state_status == MemoryStatus.PENDING
            and self.current_intent is not None
            and self.current_intent != "unsupported"
            and not self.clarification_pending
        )
