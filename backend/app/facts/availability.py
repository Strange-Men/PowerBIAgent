"""Verified, measure-aware business-data availability contracts."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from backend.app.facts.verified import FactType, VerifiedFactSet
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult, QueryShape
from backend.app.schemas.factual_context import (
    AvailableDataHorizon,
    DataAvailabilityContext,
    DataHorizonStatus,
    ObservedCoverageStatus,
)


class AvailabilityProbeBuilder:
    """Derive a read-only probe from an already canonical query plan."""

    def build_plan(self, source: CanonicalQueryPlan) -> CanonicalQueryPlan:
        if len(source.measures) != 1:
            raise ValueError("availability_probe_single_measure_required")
        if source.time_range is None:
            raise ValueError("availability_probe_temporal_dimension_required")
        date_field = source.time_range.date_field
        table_hints = source.dimension_tables or {}
        return CanonicalQueryPlan(
            normalized_question="deterministic availability verification",
            semantic_model_key=source.semantic_model_key,
            query_shape=QueryShape.GROUPED,
            measures=[source.measures[0]],
            dimensions=[date_field],
            filters=[],
            time_range=None,
            sort=None,
            top_n=None,
            requested_template=None,
            inherited_context=None,
            is_mock=False,
            dimension_tables=(
                {date_field: table_hints[date_field]}
                if date_field in table_hints
                else None
            ),
            dimension_order="desc",
        )

    def derive_horizon(
        self,
        probe_plan: CanonicalQueryPlan,
        result: QueryResult,
        facts: VerifiedFactSet,
    ) -> AvailableDataHorizon:
        if result.semantic_model_key != probe_plan.semantic_model_key:
            raise ValueError("availability_probe_model_mismatch")
        if facts.result_id != result.result_id:
            raise ValueError("availability_probe_fact_result_mismatch")
        coverage = facts.observed_data_coverage
        common = {
            "semantic_model_key": probe_plan.semantic_model_key,
            "measure": probe_plan.measures[0],
            "temporal_dimension": probe_plan.dimensions[0],
        }
        if facts.empty:
            return AvailableDataHorizon(
                status=DataHorizonStatus.EMPTY,
                source_result_id=result.result_id,
                source_fact_set_id=facts.fact_set_id,
                **common,
            )
        if coverage.status in {
            ObservedCoverageStatus.FULL,
            ObservedCoverageStatus.PARTIAL,
        }:
            return AvailableDataHorizon(
                status=DataHorizonStatus.KNOWN,
                latest_period=coverage.end_date,
                grain="month",
                source_result_id=result.result_id,
                source_fact_set_id=facts.fact_set_id,
                **common,
            )
        if coverage.status is ObservedCoverageStatus.EMPTY:
            return AvailableDataHorizon(status=DataHorizonStatus.EMPTY, **common)
        periods: list[date] = []
        dimension = probe_plan.dimensions[0]
        for fact in facts.by_type(FactType.GROUPED_METRIC):
            parsed = self._month_end(fact.dimensions.get(dimension))
            if parsed is not None:
                periods.append(parsed)
        if periods:
            return AvailableDataHorizon(
                status=DataHorizonStatus.KNOWN,
                latest_period=max(periods),
                grain="month",
                source_result_id=result.result_id,
                source_fact_set_id=facts.fact_set_id,
                **common,
            )
        return AvailableDataHorizon(status=DataHorizonStatus.UNKNOWN, **common)

    @staticmethod
    def _month_end(value: object) -> date | None:
        candidate: date | None = None
        if isinstance(value, datetime):
            candidate = value.date()
        elif isinstance(value, date):
            candidate = value
        elif isinstance(value, str):
            try:
                candidate = date.fromisoformat(value[:10])
            except ValueError:
                return None
        if candidate is None:
            return None
        return date(
            candidate.year,
            candidate.month,
            calendar.monthrange(candidate.year, candidate.month)[1],
        )
