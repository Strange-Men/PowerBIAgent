"""Plan-owned deterministic effective query scope for answers and audits."""

from __future__ import annotations

from backend.app.presentation.messages import message

from datetime import date
from typing import Any

from backend.app.presentation.formatter import PresentationFormatter
from backend.app.schemas.data_contracts import CanonicalQueryPlan, FilterOperator, QueryShape


class DeterministicQueryScopeDescriptor:
    def build(self, plan, **kwargs):
        from backend.app.presentation.locale import presentation_locale
        with presentation_locale(kwargs.get("locale", "zh-CN")) as selected:
            kwargs["locale"]=selected.value
            return self._build(plan, **kwargs)

    def _build(
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
            message('display.model_p', p0=(model_display_name or plan.semantic_model_key).strip())
        ]
        if plan.measures:
            parts.append(
                message('display.measures') + "、".join(
                    self._label(name, bindings) for name in plan.measures
                )
            )
        if plan.dimensions:
            parts.append(
                message('display.group_by') + "、".join(
                    self._label(name, bindings) for name in plan.dimensions
                )
            )
        if plan.filters:
            parts.append(
                message('display.filters') + "；".join(
                    self._filter(item, formatter, bindings)
                    for item in plan.filters
                )
            )
        if plan.time_range is not None:
            if hasattr(plan.time_range, "start_date"):
                parts.append(
                    message('display.requested_period') + self._time(
                        plan.time_range.start_date,
                        plan.time_range.end_date,
                        locale,
                    )
                )
            elif isinstance(plan.time_range, str) and plan.time_range.strip():
                # Legacy LLM AnswerContext remains non-executable; preserving
                # its text here adds context without granting canonical authority.
                parts.append(message('display.requested_period') + plan.time_range.strip())
        if plan.query_shape == QueryShape.RANKING and plan.top_n is not None:
            direction = message('display.highest') if plan.sort == "desc" else message('display.lowest')
            measure = "、".join(
                self._label(name, bindings) for name in plan.measures
            )
            parts.append(message('display.ranking_p_p_top_p', p0=measure, p1=direction, p2=plan.top_n))
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
            FilterOperator.CONTAINS: message('display.contains'),
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
        if locale == "zh-CN":
            if start.year == end.year and start.month == end.month:
                return message('display.p_p', p0=start.year, p1=start.month)
            if start.day == 1 and end.day >= 28:
                return message('display.p_p_p_p', p0=start.year, p1=start.month, p2=end.year, p3=end.month)
            return message('display.p_p_p_p_p_p', p0=start.year, p1=start.month, p2=start.day, p3=end.year, p4=end.month, p5=end.day)
        if start.year == end.year and start.month == end.month:
            return start.strftime("%Y-%m")
        return f"{start.isoformat()}–{end.isoformat()}"
