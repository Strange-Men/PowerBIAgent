"""记忆系统数据模型

固定三态：pending、committed、failed

只有满足完整成功边界时，才能提交 committed memory。
完整成功边界由 MemoryCommitEvidence 结构化表达。

版本语义：
- 没有任何 committed memory 时，当前版本为 0
- 第一轮成功提交后版本为 1
- 第二轮基于版本 1 提交后版本为 2
- pending memory 必须记录其基准版本（base_memory_version）
- 每次提交必须比较"该轮读取到的基准版本"与"当前会话最新 committed 版本"
- 版本冲突不得覆盖现有 committed memory
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.data_contracts import QueryShape, StructuredFilter, TimeRangeSpec


class MemoryStatus(str, Enum):
    """记忆状态三态机制"""

    PENDING = "pending"      # 轮次进行中，尚未达到完整成功边界
    COMMITTED = "committed"  # 轮次已完整成功，记忆已可靠提交
    FAILED = "failed"        # 轮次失败，记忆不提交


class RuntimeDataMode(str, Enum):
    """运行数据模式 — Mock 与 Real 空间隔离"""
    MOCK = "mock"
    REAL = "real"


PendingSemanticSlot = Literal[
    "measure", "dimension", "filter", "time", "analysis", "template"
]


class PendingSlotProvenance(BaseModel):
    """Authority record for one slot retained across clarification turns."""

    request_id: str
    authority: Literal[
        "semantic_catalog", "runtime_member", "deterministic_analysis"
    ]
    source: str


class PendingClarificationContext(BaseModel):
    """Non-executable semantic context for an incomplete clarification chain.

    This model is intentionally separate from ``StructuredWorkMemory``: it has
    no MemoryStatus, commit evidence, DAX, result, or response fields and can
    never enter the committed-memory version chain.
    """

    chain_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    semantic_model_key: str
    schema_fingerprint: str = Field(min_length=64, max_length=64)
    intent: Literal["data_question", "report_generation"] = "data_question"
    query_shape: Optional[QueryShape] = None
    measures: list[str] = Field(default_factory=list, max_length=1)
    dimensions: list[str] = Field(default_factory=list, max_length=1)
    filters: list[StructuredFilter] = Field(default_factory=list)
    time_range: Optional[TimeRangeSpec] = None
    sort: Optional[Literal["asc", "desc"]] = None
    top_n: Optional[int] = Field(default=None, ge=1)
    missing_slots: list[PendingSemanticSlot] = Field(default_factory=list)
    slot_provenance: dict[str, list[PendingSlotProvenance]] = Field(
        default_factory=dict
    )
    base_committed_version: int = Field(default=0, ge=0)
    runtime_mode: RuntimeDataMode = RuntimeDataMode.MOCK
    last_request_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryCommitEvidence(BaseModel):
    """结构化提交证据

    提交只有在全部必需证据满足时允许。
    版本匹配由 Repository 在原子提交阶段检查和记录，
    调用方不得提前伪造 version_matches=True。
    """

    intent_valid: bool = False
    request_allowed: bool = False
    query_plan_valid: bool = False
    dax_valid: bool = False
    tool_execution_succeeded: bool = False
    query_result_valid: bool = False
    response_valid: bool = False
    version_matches: bool = False  # 由 Repository 在原子提交时设置
    runtime_mode: RuntimeDataMode = RuntimeDataMode.MOCK
    failure_reason: Optional[str] = None

    @property
    def business_satisfied(self) -> bool:
        """业务条件全部满足（不含版本匹配）"""
        return all([
            self.intent_valid,
            self.request_allowed,
            self.query_plan_valid,
            self.dax_valid,
            self.tool_execution_succeeded,
            self.query_result_valid,
            self.response_valid,
        ])

    @property
    def all_satisfied(self) -> bool:
        """所有必需证据满足（含版本匹配）"""
        return self.business_satisfied and self.version_matches


class MemoryCorrectionRecord(BaseModel):
    """结构化纠正记录"""
    field: str
    old_value: Optional[object] = None
    new_value: Optional[object] = None
    reason: Optional[str] = None
    corrected_at: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class StructuredWorkMemory(BaseModel):
    """结构化工作记忆

    当前轮次的分析上下文，包含指标、维度、时间、筛选等要素。
    只有 status == committed 的记忆才会在 Context Assembly 中加载。

    版本语义：
    - base_memory_version: 开始本轮时读取到的 committed 版本（0 表示无历史）
    - memory_version: 提交成功后递增为 base + 1
    - 状态和版本只能由 Repository 成功提交时改变
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
    filters: list[dict] = Field(default_factory=list, description="筛选条件")
    time_range: Optional[TimeRangeSpec | str] = Field(
        default=None, description="结构化时间范围；旧 Mock 字符串仅作兼容"
    )
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
    base_memory_version: int = Field(default=0, ge=0, description="本轮开始时读取到的 committed 版本")
    memory_version: int = Field(default=0, ge=0, description="当前版本号 — 成功 Commit 后递增为 base+1")
    state_status: MemoryStatus = Field(default=MemoryStatus.PENDING, description="记忆状态")

    # 失败信息
    failure_reason: Optional[str] = Field(default=None, description="失败原因")
    failure_stage: Optional[str] = Field(default=None, description="失败阶段")

    # 来源标记
    is_mock: bool = Field(default=False, description="是否由 Mock LLM 生成")
    runtime_mode: RuntimeDataMode = Field(default=RuntimeDataMode.MOCK, description="运行模式")
    llm_provider: Optional[str] = Field(default=None, description="LLM Provider 名称")
    powerbi_provider: Optional[str] = Field(default=None, description="Power BI Provider 名称")

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="最后更新时间")

    # 审计
    correction_history: list[MemoryCorrectionRecord] = Field(
        default_factory=list, description="纠正记录历史"
    )
    commit_evidence: Optional[MemoryCommitEvidence] = Field(
        default=None, description="最近一次提交证据"
    )

    @field_validator("filters")
    @classmethod
    def validate_canonical_filters(cls, filters: list[dict]) -> list[dict]:
        """Reject semantically corrupt filters while preserving legacy dict shape."""
        for index, item in enumerate(filters):
            try:
                StructuredFilter.model_validate(item)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"committed_memory_filter_invalid:{index}"
                ) from exc
        return filters

    def _bump_version(self) -> None:
        """递增 memory_version（仅 Repository 内部使用）"""
        self.memory_version = self.base_memory_version + 1
        self.updated_at = datetime.utcnow()

    def _mark_committed(self, evidence: MemoryCommitEvidence) -> None:
        """标记为已提交（仅 Repository 内部使用）

        Raises:
            ValueError: 状态为 failed 时不可提交
        """
        if self.state_status == MemoryStatus.FAILED:
            raise ValueError("failed 状态的记忆不可标记为 committed")
        self.state_status = MemoryStatus.COMMITTED
        self.commit_evidence = evidence
        self._bump_version()

    def _mark_failed(self, reason: Optional[str] = None, stage: Optional[str] = None) -> None:
        """标记为失败（仅 Repository 内部使用）

        Args:
            reason: 失败原因
            stage: 失败阶段
        """
        self.state_status = MemoryStatus.FAILED
        self.failure_reason = reason
        self.failure_stage = stage
        self.updated_at = datetime.utcnow()

    def is_committable(self) -> bool:
        """检查是否满足基本提交条件（不检查版本/证据，由 Repository 负责）"""
        return (
            self.state_status == MemoryStatus.PENDING
            and self.current_intent is not None
            and self.current_intent not in ("unsupported", "clarification")
            and not self.clarification_pending
        )

    def add_correction_record(self, record: MemoryCorrectionRecord) -> None:
        """添加纠正审计记录"""
        self.correction_history.append(record)
        self.updated_at = datetime.utcnow()
