"""IntentContextSnapshot — M1.2 真实意图识别的安全上下文模型

从 committed memory 中提取白名单字段，避免将完整 StructuredWorkMemory、
DAX、查询结果或全量 Trace 发送给 LLM。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field, model_validator

from backend.app.intent.models import FilterSpec


class IntentContextSnapshot(BaseModel):
    """意图识别的安全上下文快照

    只包含允许发送给 LLM 的字段白名单子集。
    禁止发送 pending/failed memory、完整历史对话、DAX、原始查询结果。
    """

    semantic_model_key: Optional[str] = Field(default=None, description="语义模型 Key")
    report_template_key: Optional[str] = Field(default=None, description="报表模板 Key")
    current_intent: Optional[str] = Field(default=None, description="上一轮意图类型")
    measures: list[str] = Field(default_factory=list, description="已提交的指标列表")
    dimensions: list[str] = Field(default_factory=list, description="已提交的维度列表")
    filters: list[FilterSpec] = Field(default_factory=list, description="已提交的筛选条件")
    time_range: Optional[str] = Field(default=None, description="已提交的时间范围")
    clarification_pending: bool = Field(default=False, description="是否待澄清")
    clarification_question: Optional[str] = Field(default=None, description="待澄清问题")

    model_config = {
        "extra": "forbid",
        "frozen": True,
    }

    @model_validator(mode="after")
    def _strip_strings(self) -> "IntentContextSnapshot":
        """所有字符串执行首尾空白清理；列表中的空字符串移除。"""
        object.__setattr__(self, "measures", [m for m in self.measures if m.strip()])
        object.__setattr__(self, "dimensions", [d for d in self.dimensions if d.strip()])
        if self.current_intent is not None:
            object.__setattr__(self, "current_intent", self.current_intent.strip() or None)
        if self.time_range is not None:
            object.__setattr__(self, "time_range", self.time_range.strip() or None)
        return self

    @classmethod
    def from_committed_memory(
        cls,
        committed_memory: Optional[Mapping[str, Any]],
        *,
        semantic_model_key: Optional[str] = None,
        report_template_key: Optional[str] = None,
    ) -> "IntentContextSnapshot":
        """从已提交 Memory 中提取白名单字段。

        安全规则：
        - committed_memory=None → 返回空上下文
        - state_status="committed" → 只提取白名单字段
        - state_status="pending" 或 "failed" → 不提取任何业务上下文
        - 状态缺失或非法 → 按非 committed 处理

        白名单字段：semantic_model_key, report_template_key,
        current_intent, measures, dimensions, filters, time_range,
        clarification_pending, clarification_question。

        不会提取：conversation_id, request_id, last_query_plan,
        last_dax, last_query_result_id, last_result_summary,
        memory_version, state_status, failure_reason, is_mock 等。
        """
        if committed_memory is None:
            return cls(
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
            )

        # 检查 state_status：只有 committed 才提取业务上下文
        state_status = committed_memory.get("state_status")
        if state_status != "committed":
            # pending、failed、缺失或非法状态 → 不继承业务上下文
            return cls(
                semantic_model_key=semantic_model_key,
                report_template_key=report_template_key,
            )

        # 白名单提取（仅 state_status="committed" 时执行）
        raw_filters = committed_memory.get("filters", [])
        parsed_filters: list[FilterSpec] = []
        for f in raw_filters:
            if isinstance(f, dict):
                try:
                    parsed_filters.append(FilterSpec(**f))
                except Exception:
                    pass  # 跳过不合法的筛选
            elif isinstance(f, FilterSpec):
                parsed_filters.append(f)

        return cls(
            semantic_model_key=(
                committed_memory.get("semantic_model_key") or semantic_model_key
            ),
            report_template_key=(
                committed_memory.get("report_template_key") or report_template_key
            ),
            current_intent=committed_memory.get("current_intent"),
            measures=list(committed_memory.get("measures", [])),
            dimensions=list(committed_memory.get("dimensions", [])),
            filters=parsed_filters,
            time_range=committed_memory.get("time_range"),
            clarification_pending=bool(
                committed_memory.get("clarification_pending", False)
            ),
            clarification_question=committed_memory.get("clarification_question"),
        )
