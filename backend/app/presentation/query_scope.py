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
        locale: str = "zh-CN",
    ) -> str:
        bindings = display_bindings or {}
        formatter = PresentationFormatter(locale=locale)
        parts: list[str] = []
        if plan.time_range is not None:
            if hasattr(plan.time_range, "start_date"):
                parts.append(self._time(
                    plan.time_range.start_date, plan.time_range.end_date, locale
                ))
            elif isinstance(plan.time_range, str) and plan.time_range.strip():
                # Legacy LLM AnswerContext remains non-executable; preserving
                # its text here adds context without granting canonical authority.
                parts.append(plan.time_range.strip())
        for item in plan.filters:
            values = item.value if item.operator == FilterOperator.IN_SET and isinstance(item.value, (list, tuple)) else [item.value]
            parts.append("、".join(formatter.format(value) for value in values))
        if plan.dimensions:
            dimension_labels = "、".join(self._label(name, bindings) for name in plan.dimensions)
            if plan.query_shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
                parts.append(f"按{dimension_labels}趋势")
            elif plan.query_shape != QueryShape.ENTITY_LIST:
                parts.append(f"按{dimension_labels}")
            else:
                parts.append(dimension_labels)
        if plan.measures:
            measure = "、".join(self._label(name, bindings) for name in plan.measures)
            if plan.query_shape == QueryShape.RANKING and plan.top_n is not None:
                direction = "最高" if plan.sort == "desc" else "最低"
                measure = f"{measure}{direction}Top{plan.top_n}"
            parts.append(measure)
        return " · ".join(part for part in parts if part)

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
