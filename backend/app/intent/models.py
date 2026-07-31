"""意图识别模块 — IntentType 与 IntentSpec Pydantic 模型"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class IntentType(str, Enum):
    """四类基础意图"""

    DATA_QUESTION = "data_question"
    REPORT_GENERATION = "report_generation"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


class IntentSpec(BaseModel):
    """结构化意图识别结果

    意图识别必须结合已提交的 committed memory 上下文：
    - "只看华南" → 继承已有指标和时间，替换筛选条件
    - "改成今年" → 继承已有指标和维度，替换时间范围
    - "换成订单数" → 继承已有维度和时间，替换指标
    - "生成周报" → 可复用已验证的查询上下文
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
    detected_filters: list[dict[str, str]] = Field(default_factory=list, description="检测到的筛选条件")
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

    @field_validator("unsupported_reason")
    @classmethod
    def unsupported_reason_required(cls, v: Optional[str], info) -> Optional[str]:
        intent = info.data.get("intent") if info.data else None
        if intent == IntentType.UNSUPPORTED and not v:
            raise ValueError("unsupported_reason is required when intent is unsupported")
        return v
