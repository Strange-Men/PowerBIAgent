"""Canonical query-shape completeness checks.

Language coverage belongs to the Understanding Layer. This module only
validates already-bound canonical execution slots before deterministic DAX.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from backend.app.query_plan.clarification_reasons import ClarificationReason
from backend.app.query_plan.semantic_catalog import SemanticCatalog
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    FilterOperator,
    QueryShape,
)


class CanonicalShapeCompletenessError(ValueError):
    _REASONS: ClassVar[dict[str, ClarificationReason]] = {
        "canonical_shape_obligation_mismatch": ClarificationReason.UNSUPPORTED_SEMANTIC_REQUEST,
        "canonical_shape_measure_required": ClarificationReason.MEASURE_UNRESOLVED,
        "canonical_shape_entity_list_dimension_required": ClarificationReason.DIMENSION_UNRESOLVED,
        "canonical_shape_grouped_dimension_required": ClarificationReason.DIMENSION_UNRESOLVED,
        "canonical_shape_ranking_dimension_required": ClarificationReason.RANKING_INFORMATION_INCOMPLETE,
        "canonical_shape_ranking_sort_required": ClarificationReason.RANKING_INFORMATION_INCOMPLETE,
        "canonical_shape_ranking_top_n_required": ClarificationReason.RANKING_INFORMATION_INCOMPLETE,
        "canonical_shape_member_set_single_field_required": ClarificationReason.INCOMPLETE_MEMBER_SET,
        "canonical_shape_member_set_operator_required": ClarificationReason.INCOMPLETE_MEMBER_SET,
        "canonical_shape_member_set_values_required": ClarificationReason.INCOMPLETE_MEMBER_SET,
        "canonical_shape_member_set_duplicate_value": ClarificationReason.INCOMPLETE_MEMBER_SET,
        "canonical_shape_filtered_filter_required": ClarificationReason.FILTER_FIELD_UNRESOLVED,
        "canonical_shape_filtered_filter_values_required": ClarificationReason.INCOMPLETE_MEMBER_SET,
        "canonical_shape_trend_temporal_dimension_required": ClarificationReason.DIMENSION_UNRESOLVED,
        "canonical_shape_trend_single_dimension_required": ClarificationReason.DIMENSION_UNRESOLVED,
        "canonical_shape_trend_ascending_required": ClarificationReason.INCOMPLETE_TIME_RANGE,
        "canonical_shape_bounded_trend_time_required": ClarificationReason.INCOMPLETE_TIME_RANGE,
        "canonical_shape_bounded_trend_month_grain_required": ClarificationReason.INCOMPLETE_TIME_RANGE,
    }

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
        self.clarification_reason = self._REASONS.get(
            code, ClarificationReason.UNSUPPORTED_SEMANTIC_REQUEST
        )


class CanonicalShapeCompletenessReport(BaseModel):
    complete: bool = True
    shape: QueryShape
    required_slots: tuple[str, ...]
    scope_fields: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


class CanonicalShapeCompletenessGate:
    """Prove shape-specific canonical slots before deterministic DAX."""

    def validate(
        self,
        plan: CanonicalQueryPlan,
        *,
        catalog: SemanticCatalog | None = None,
        expected_shape: QueryShape | None = None,
        runtime_temporal_grouping_ids: tuple[str, ...] = (),
    ) -> CanonicalShapeCompletenessReport:
        shape = plan.query_shape or QueryShape.SCALAR
        if expected_shape is not None and shape != expected_shape:
            self._fail("canonical_shape_obligation_mismatch")
        if shape != QueryShape.ENTITY_LIST and not plan.measures:
            self._fail("canonical_shape_measure_required")
        required: tuple[str, ...]
        if shape == QueryShape.SCALAR:
            required = ("measure",)
        elif shape == QueryShape.ENTITY_LIST:
            required = ("dimension",)
            if not plan.dimensions:
                self._fail("canonical_shape_entity_list_dimension_required")
        elif shape == QueryShape.GROUPED:
            required = ("measure", "dimension")
            if not plan.dimensions:
                self._fail("canonical_shape_grouped_dimension_required")
        elif shape == QueryShape.RANKING:
            required = ("measure", "dimension", "sort", "top_n")
            if not plan.dimensions:
                self._fail("canonical_shape_ranking_dimension_required")
            if plan.sort is None:
                self._fail("canonical_shape_ranking_sort_required")
            if plan.top_n is None:
                self._fail("canonical_shape_ranking_top_n_required")
        elif shape == QueryShape.MEMBER_SET:
            required = ("authoritative_filter_field", "complete_member_set")
            if len(plan.filters) != 1:
                self._fail("canonical_shape_member_set_single_field_required")
            item = plan.filters[0]
            if item.operator != FilterOperator.IN_SET:
                self._fail("canonical_shape_member_set_operator_required")
            if not isinstance(item.value, (list, tuple)) or not item.value:
                self._fail("canonical_shape_member_set_values_required")
            if len({str(value) for value in item.value}) != len(item.value):
                self._fail("canonical_shape_member_set_duplicate_value")
        elif shape == QueryShape.FILTERED_AGGREGATION:
            required = ("measure", "complete_filter")
            if not plan.filters:
                self._fail("canonical_shape_filtered_filter_required")
            if any(
                item.operator == FilterOperator.IN_SET
                and (not isinstance(item.value, (list, tuple)) or not item.value)
                for item in plan.filters
            ):
                self._fail("canonical_shape_filtered_filter_values_required")
        elif shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
            required = ("measure", "temporal_grouping") + (
                ("bounded_time_range",)
                if shape == QueryShape.BOUNDED_TREND
                else ()
            )
            if not plan.dimensions or not self._has_temporal_grouping(
                plan, catalog, runtime_temporal_grouping_ids
            ):
                self._fail("canonical_shape_trend_temporal_dimension_required")
            if len(plan.dimensions) != 1:
                self._fail("canonical_shape_trend_single_dimension_required")
            if plan.dimension_order != "asc":
                self._fail("canonical_shape_trend_ascending_required")
            if shape == QueryShape.BOUNDED_TREND and plan.time_range is None:
                self._fail("canonical_shape_bounded_trend_time_required")
            if (
                shape == QueryShape.BOUNDED_TREND
                and plan.time_range is not None
                and plan.time_range.grain != "month"
            ):
                self._fail("canonical_shape_bounded_trend_month_grain_required")
        else:  # pragma: no cover - enum exhaustiveness
            self._fail("canonical_shape_unsupported")
        return CanonicalShapeCompletenessReport(
            shape=shape,
            required_slots=required,
            scope_fields=tuple([
                *plan.measures,
                *plan.dimensions,
                *(item.field for item in plan.filters),
                *([plan.time_range.date_field] if plan.time_range else []),
            ]),
        )

    @staticmethod
    def _has_temporal_grouping(
        plan: CanonicalQueryPlan,
        catalog: SemanticCatalog | None,
        runtime_temporal_grouping_ids: tuple[str, ...] = (),
    ) -> bool:
        if plan.dimension_order != "asc":
            return False
        if catalog is None:
            return True
        hints = plan.dimension_tables or {}
        for name in plan.dimensions:
            matches = [
                obj
                for obj in catalog.objects
                if obj.canonical_name == name
                and (hints.get(name) is None or obj.table_name == hints[name])
            ]
            if any(
                obj.temporal_grouping is not None
                or obj.object_id in runtime_temporal_grouping_ids
                for obj in matches
            ):
                return True
        return False

    @staticmethod
    def _fail(code: str) -> None:
        raise CanonicalShapeCompletenessError(code)
