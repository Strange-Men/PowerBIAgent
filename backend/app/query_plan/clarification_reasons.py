"""Deterministic semantic clarification categories and user-facing prompts."""

from __future__ import annotations

from enum import Enum


class ClarificationReason(str, Enum):
    DIMENSION_UNRESOLVED = "dimension_unresolved"
    DIMENSION_AMBIGUOUS = "dimension_ambiguous"
    FILTER_FIELD_UNRESOLVED = "filter_field_unresolved"
    FILTER_FIELD_AMBIGUOUS = "filter_field_ambiguous"
    MEMBER_NO_MATCH = "member_no_match"
    MEMBER_AMBIGUOUS = "member_ambiguous"
    INCOMPLETE_MEMBER_SET = "incomplete_member_set"
    INCOMPLETE_TIME_RANGE = "incomplete_time_range"
    RANKING_INFORMATION_INCOMPLETE = "ranking_information_incomplete"
    MEASURE_UNRESOLVED = "measure_unresolved"
    UNSUPPORTED_SEMANTIC_REQUEST = "unsupported_semantic_request"


_QUESTIONS: dict[ClarificationReason, str] = {
    ClarificationReason.DIMENSION_UNRESOLVED: "未能确定分析维度，请明确要按哪个维度比较。",
    ClarificationReason.DIMENSION_AMBIGUOUS: "分析维度存在多个匹配，请明确要使用哪一个。",
    ClarificationReason.FILTER_FIELD_UNRESOLVED: "未能确定筛选字段，请同时说明字段和值。",
    ClarificationReason.FILTER_FIELD_AMBIGUOUS: "筛选字段存在多个匹配，请明确字段和值。",
    ClarificationReason.MEMBER_NO_MATCH: "筛选值未匹配模型中的任何成员，请确认后重试。",
    ClarificationReason.MEMBER_AMBIGUOUS: "筛选值匹配了多个成员，请明确选择。",
    ClarificationReason.INCOMPLETE_MEMBER_SET: "成员集合不完整，请明确并列条件中的每一个筛选成员。",
    ClarificationReason.INCOMPLETE_TIME_RANGE: "时间范围不完整，请明确开始月份、结束月份和月度粒度。",
    ClarificationReason.RANKING_INFORMATION_INCOMPLETE: "排名信息不完整，请明确指标、维度、排序方向和数量。",
    ClarificationReason.MEASURE_UNRESOLVED: "未能确定业务指标，请明确要查询的指标。",
    ClarificationReason.UNSUPPORTED_SEMANTIC_REQUEST: "当前模型或查询能力不支持该业务条件，请调整后重试。",
}


def clarification_question(reason: ClarificationReason) -> str:
    """Return code-owned wording for one structured clarification reason."""

    return _QUESTIONS[reason]
