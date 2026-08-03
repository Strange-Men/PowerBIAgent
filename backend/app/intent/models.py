"""意图识别模块 — IntentType、FilterSpec 与 IntentSpec Pydantic 模型"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class IntentType(str, Enum):
    """四类基础意图"""

    DATA_QUESTION = "data_question"
    REPORT_GENERATION = "report_generation"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


class FilterOperator(str, Enum):
    """筛选操作符"""
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN_SET = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"


FilterValue = Union[str, int, float, bool, date, datetime]


class FilterSpec(BaseModel):
    """结构化筛选条件

    不再依赖任意 dict[str, str]，而是使用明确的结构化模型。
    value 允许数字、布尔、日期字符串和文本。
    """

    field: str = Field(..., min_length=1, description="筛选字段名")
    operator: FilterOperator = Field(default=FilterOperator.EQ, description="操作符")
    value: FilterValue = Field(..., description="筛选值（文本、数字、布尔或日期）")

    model_config = {"extra": "forbid"}

    def to_legacy_dict(self) -> dict[str, str]:
        """转换为旧版 dict[str, str] 格式（向后兼容）"""
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": str(self.value),
        }


class IntentSpec(BaseModel):
    """结构化意图识别结果

    意图识别必须结合已提交的 committed memory 上下文：
    - "只看华南" → 继承已有指标和时间，替换筛选条件
    - "改成今年" → 继承已有指标和维度，替换时间范围
    - "换成订单数" → 继承已有维度和时间，替换指标
    - "生成周报" → 可复用已验证的查询上下文

    跨字段一致性规则：
    1. clarification → needs_clarification=True + 有非空 clarification_question
    2. 非 clarification → 不应携带待澄清状态
    3. unsupported → 必须有 unsupported_reason
    4. 非 unsupported → 不应携带拒绝原因
    5. normalized_question 去除纯空格后不能为空
    """

    intent: IntentType = Field(..., description="意图类型")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 [0, 1]")
    normalized_question: str = Field(..., min_length=1, description="标准化后的问题文本")

    # 澄清
    needs_clarification: bool = Field(default=False, description="是否需要向用户澄清")
    clarification_question: Optional[str] = Field(default=None, description="澄清问题文本")

    # 上下文继承
    inherited_context: Optional[str] = Field(default=None, description="从 committed memory 继承的上下文摘要")

    # 检测到的分析要素
    detected_measures: list[str] = Field(default_factory=list, description="检测到的指标")
    detected_dimensions: list[str] = Field(default_factory=list, description="检测到的维度")
    detected_filters: list[FilterSpec] = Field(default_factory=list, description="检测到的筛选条件")
    detected_time_range: Optional[str] = Field(default=None, description="检测到的时间范围")

    # 报表相关
    requested_template: Optional[str] = Field(default=None, description="请求的报表模板名称")

    # 拒绝
    unsupported_reason: Optional[str] = Field(default=None, description="拒绝原因（仅 unsupported 意图）")

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("normalized_question")
    @classmethod
    def normalized_question_not_blank(cls, v: str) -> str:
        """去除纯空格后不能为空"""
        if not v.strip():
            raise ValueError("normalized_question must not be blank or whitespace-only")
        return v

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _clean_and_validate(self) -> "IntentSpec":
        """字符串清理 + 跨字段一致性验证

        清理规则：
        - 所有字符串首尾空白清理
        - 列表中的空字符串移除
        - 指标和维度去重保持原顺序
        - normalized_question 不能为空
        - confidence 必须在 0-1
        """
        # ── 字符串清理 ──
        object.__setattr__(self, "normalized_question", self.normalized_question.strip())
        if self.clarification_question is not None:
            cleaned = self.clarification_question.strip()
            object.__setattr__(self, "clarification_question", cleaned or None)
        if self.unsupported_reason is not None:
            cleaned = self.unsupported_reason.strip()
            object.__setattr__(self, "unsupported_reason", cleaned or None)
        if self.inherited_context is not None:
            cleaned = self.inherited_context.strip()
            object.__setattr__(self, "inherited_context", cleaned or None)
        if self.detected_time_range is not None:
            cleaned = self.detected_time_range.strip()
            object.__setattr__(self, "detected_time_range", cleaned or None)
        if self.requested_template is not None:
            cleaned = self.requested_template.strip()
            object.__setattr__(self, "requested_template", cleaned or None)

        # ── 列表清理：去空字符串 + 去重保持原顺序 ──
        measures = []
        seen_m = set()
        for m in self.detected_measures:
            if isinstance(m, str) and m.strip():
                m_clean = m.strip()
                if m_clean not in seen_m:
                    measures.append(m_clean)
                    seen_m.add(m_clean)
        object.__setattr__(self, "detected_measures", measures)

        dimensions = []
        seen_d = set()
        for d in self.detected_dimensions:
            if isinstance(d, str) and d.strip():
                d_clean = d.strip()
                if d_clean not in seen_d:
                    dimensions.append(d_clean)
                    seen_d.add(d_clean)
        object.__setattr__(self, "detected_dimensions", dimensions)

        # ── normalized_question 不能为空 ──
        if not self.normalized_question:
            raise ValueError("normalized_question must not be empty")

        # ── confidence 必须在 0-1 ──
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

        # ── 跨字段规则 ──
        # 规则1：clarification 必须有 needs_clarification=True 和非空 clarification_question
        if self.intent == IntentType.CLARIFICATION:
            if not self.needs_clarification:
                raise ValueError(
                    "clarification intent must have needs_clarification=True"
                )
            if not self.clarification_question:
                raise ValueError(
                    "clarification intent must have non-empty clarification_question"
                )

        # 规则2：非 clarification 不应携带待澄清状态
        if self.intent != IntentType.CLARIFICATION:
            if self.needs_clarification:
                raise ValueError(
                    f"intent '{self.intent.value}' should not have needs_clarification=True"
                )

        # 规则3：unsupported 必须有 unsupported_reason
        if self.intent == IntentType.UNSUPPORTED:
            if not self.unsupported_reason:
                raise ValueError(
                    "unsupported intent must have non-empty unsupported_reason"
                )

        # 规则4：非 unsupported 不应携带拒绝原因
        if self.intent != IntentType.UNSUPPORTED:
            if self.unsupported_reason is not None and self.unsupported_reason:
                raise ValueError(
                    f"intent '{self.intent.value}' should not have unsupported_reason"
                )

        # 规则5：data_question 和 report_generation 不应有 clarification 字段
        if self.intent in (IntentType.DATA_QUESTION, IntentType.REPORT_GENERATION):
            if self.clarification_question is not None:
                raise ValueError(
                    f"intent '{self.intent.value}' should not have clarification_question"
                )
            if self.unsupported_reason is not None:
                raise ValueError(
                    f"intent '{self.intent.value}' should not have unsupported_reason"
                )

        return self
