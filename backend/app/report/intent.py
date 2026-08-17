"""Deterministic report-intent resolution for the sales_report design system.

The user's natural language is resolved to registry-owned section IDs by
ordinary code.  A bounded LLM draft (see deepseek_report_intent_service.py)
may add registry-owned IDs as a weak signal; the deterministic signal is
always the floor, and an explicit scope limiter ("只看…") ignores LLM
additions entirely.  Unknown IDs are dropped, never interpreted.

This module contains no numbers, no DAX, no HTML, no free field names and no
visual types — only the fixed analysis-goal registry.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.report.capability import (
    ANALYSIS_SECTION_ORDER,
    KPI_SECTION_ORDER,
    SectionKey,
    parse_section_ids,
)

# ── Fixed analysis-goal registry (labels + trigger terms, both deterministic)
# Only these IDs exist; the LLM draft and the NL matcher share this registry.

SECTION_TRIGGERS: dict[SectionKey, tuple[str, ...]] = {
    SectionKey.SALES_KPI: ("销售额",),
    SectionKey.QUANTITY_KPI: ("销量",),
    SectionKey.ORDERS_KPI: ("订单数", "订单量", "总订单"),
    SectionKey.AOV_KPI: ("客单价", "平均订单金额", "均价"),
    SectionKey.TIME_TREND: ("趋势", "走势", "按月", "月度"),
    SectionKey.CATEGORY_CONTRIBUTION: ("品类", "类别", "分类构成", "类目"),
    SectionKey.REGION_COMPARISON: ("区域", "地区", "地域"),
    SectionKey.TOP_PRODUCTS: ("产品", "商品"),
    SectionKey.TOP_CUSTOMERS: ("客户",),
}

_FULL_MARKERS = ("完整", "全面", "全部", "整体", "所有分析", "详细", "总览")
_LIMITER_MARKERS = ("只看", "只想看", "只要", "仅看", "仅需", "只要看")

_FULL_REQUESTED_IDS = tuple(item.value for item in (*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER))


class ReportIntentDraft(BaseModel):
    """Bounded LLM weak-signal output: registry-owned analysis goal IDs only.

    The LLM never outputs DAX, HTML, CSS, numbers, field names, visual types
    or queries — only IDs from the fixed registry.  Malformed or unknown IDs
    are discarded by parse_section_ids() (fail closed).
    """

    report_section_ids: list[str] = Field(default_factory=list)


class ReportIntentSignal(BaseModel):
    """Deterministic resolution of the report-intent request.

    ``requested_ids``: registry-owned analysis-goal IDs in fixed registry
    order (deduplicated).  ``scope_limited``: user explicitly narrowed scope
    ("只看…") so no LLM additions and no default-full apply.
    ``llm_draft_ids``: the (optionally merged) valid LLM weak-signal IDs.
    """

    requested_ids: tuple[str, ...] = ()
    scope_limited: bool = False
    llm_used: bool = False
    llm_draft_ids: tuple[str, ...] = ()

    model_config = {"frozen": True}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def resolve_report_intent(
    user_input: str,
    llm_draft: Any = None,
) -> ReportIntentSignal:
    """Resolve user input (+ optional bounded LLM draft) to section IDs.

    The LLM draft is a weak signal only: its IDs must be registry-owned
    (parse_section_ids) and are merged by union unless the user explicitly
    narrowed scope.  The deterministic match is always present.
    """
    normalized = user_input or ""
    scope_limited = _contains_any(normalized, _LIMITER_MARKERS)

    triggered: list[SectionKey] = []
    for key in (*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER):
        if _contains_any(normalized, SECTION_TRIGGERS[key]) and key not in triggered:
            triggered.append(key)

    if not triggered:
        if _contains_any(normalized, _FULL_MARKERS) or not scope_limited:
            # No specific analysis goal → the full capability request is the
            # fixed default for a sales report request (matches the M3
            # baseline "生成销售分析报表" behavior).  A limiter with no
            # matched goal yields nothing (fail closed).
            triggered = list((*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER))
    elif not scope_limited:
        # Anchor: every analysis section carries the sales KPI for context,
        # matching "看看销售趋势 → Sales KPI + Trend".
        if any(key in ANALYSIS_SECTION_ORDER for key in triggered) and (
            SectionKey.SALES_KPI not in triggered
        ):
            triggered.insert(0, SectionKey.SALES_KPI)
        if _contains_any(normalized, _FULL_MARKERS):
            triggered = list((*KPI_SECTION_ORDER, *ANALYSIS_SECTION_ORDER))

    deterministic = tuple(item.value for item in triggered)

    valid_draft = parse_section_ids(
        llm_draft.report_section_ids
        if isinstance(llm_draft, BaseModel) and hasattr(llm_draft, "report_section_ids")
        else llm_draft
    )
    merged: list[str] = []
    for item in (*deterministic, *valid_draft):
        if not scope_limited and item not in merged:
            merged.append(item)
    if scope_limited:
        merged = list(deterministic)

    return ReportIntentSignal(
        requested_ids=tuple(merged),
        scope_limited=scope_limited,
        llm_used=bool(valid_draft),
        llm_draft_ids=valid_draft,
    )


def full_requested_ids() -> tuple[str, ...]:
    """The fixed full-capability request (used by tests and smoke scripts)."""
    return _FULL_REQUESTED_IDS
