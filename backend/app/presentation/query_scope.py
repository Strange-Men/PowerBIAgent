"""Plan-owned deterministic effective query scope for answers and audits."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.app.presentation.formatter import PresentationFormatter
from backend.app.schemas.data_contracts import CanonicalQueryPlan, FilterOperator, QueryShape


class DeterministicQueryScopeDescriptor:
    def build(
        self,
        plan: CanonicalQueryPlan,
        *,
        display_bindings: dict[str, Any] | None = None,
        model_display_name: str | None = None,
        locale: str = "zh-CN",
    ) -> str:
        bindings = display_bindings or {}
        formatter = PresentationFormatter(locale=locale)
        parts: list[str] = [
            f"模型：{(model_display_name or plan.semantic_model_key).strip()}"
        ]
        if plan.measures:
            parts.append(
                "指标：" + "、".join(
                    self._label(name, bindings) for name in plan.measures
                )
            )
        if plan.dimensions:
            parts.append(
                "分组：" + "、".join(
                    self._label(name, bindings) for name in plan.dimensions
                )
            )
        if plan.filters:
            parts.append(
                "筛选：" + "；".join(
                    self._filter(item, formatter, bindings)
                    for item in plan.filters
                )
            )
        if plan.time_range is not None:
            if hasattr(plan.time_range, "start_date"):
                parts.append(
                    "查询时间：" + self._time(
                        plan.time_range.start_date,
                        plan.time_range.end_date,
                        locale,
                    )
                )
            elif isinstance(plan.time_range, str) and plan.time_range.strip():
                # Legacy LLM AnswerContext remains non-executable; preserving
                # its text here adds context without granting canonical authority.
                parts.append("查询时间：" + plan.time_range.strip())
        if plan.query_shape == QueryShape.RANKING and plan.top_n is not None:
            direction = "最高" if plan.sort == "desc" else "最低"
            measure = "、".join(
                self._label(name, bindings) for name in plan.measures
            )
            parts.append(f"排名：{measure}{direction}Top{plan.top_n}")
        return " · ".join(part for part in parts if part)

    @staticmethod
    def canonical_evidence(plan: CanonicalQueryPlan) -> dict[str, Any]:
        return {
            "selected_model": plan.semantic_model_key,
            "measures": list(plan.measures),
            "grouping_dimensions": list(plan.dimensions),
            "filters": [item.model_dump(mode="json") for item in plan.filters],
            "requested_time_range": (
                plan.time_range.model_dump(mode="json")
                if plan.time_range is not None
                else None
            ),
            "ranking": (
                {
                    "direction": plan.sort,
                    "top_n": plan.top_n,
                    "measure": plan.measures[0] if plan.measures else None,
                }
                if plan.query_shape == QueryShape.RANKING
                else None
            ),
        }

    @classmethod
    def _filter(
        cls,
        item: Any,
        formatter: PresentationFormatter,
        bindings: dict[str, Any],
    ) -> str:
        values = (
            item.value
            if item.operator == FilterOperator.IN_SET
            and isinstance(item.value, (list, tuple))
            else [item.value]
        )
        operator = {
            FilterOperator.EQ: "=",
            FilterOperator.NE: "≠",
            FilterOperator.GT: ">",
            FilterOperator.GTE: "≥",
            FilterOperator.LT: "<",
            FilterOperator.LTE: "≤",
            FilterOperator.IN_SET: "∈",
            FilterOperator.NOT_IN: "∉",
            FilterOperator.CONTAINS: "包含",
        }[item.operator]
        return (
            f"{cls._label(item.field, bindings)}{operator}"
            + "、".join(formatter.format(value) for value in values)
        )

    @staticmethod
    def _label(canonical: str, bindings: dict[str, Any]) -> str:
        direct = bindings.get(canonical)
        if direct is not None:
            return direct.display_name
        matches = [
            value.display_name for value in bindings.values()
            if getattr(value, "canonical_name", None) == canonical
        ]
        return matches[0] if len(set(matches)) == 1 else canonical

    @staticmethod
    def _time(start: date, end: date, locale: str) -> str:
        if locale.casefold().startswith("zh"):
            if start.year == end.year and start.month == end.month:
                return f"{start.year}年{start.month}月"
            if start.day == 1 and end.day >= 28:
                return f"{start.year}年{start.month}月–{end.year}年{end.month}月"
            return f"{start.year}年{start.month}月{start.day}日–{end.year}年{end.month}月{end.day}日"
        if start.year == end.year and start.month == end.month:
            return start.strftime("%Y-%m")
        return f"{start.isoformat()}–{end.isoformat()}"
