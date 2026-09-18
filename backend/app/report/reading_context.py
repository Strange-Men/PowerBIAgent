"""Deterministic assembly helpers for the complex-report reading contract."""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from backend.app.facts import FactType, VerifiedFactSet
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult
from backend.app.schemas.factual_context import (
    DataAvailabilityContext,
    ObservedCoverageStatus,
    ObservedDataCoverage,
)
from backend.app.schemas.report_context import (
    ActiveFilterContext,
    ActiveFilterState,
    AnalysisPeriodState,
    ExceptionAssessment,
    MetricDefinition,
    MetricDefinitionFacet,
    ReportAnalysisPeriod,
    ReportDataFreshness,
    ReportDataSourceKind,
    ReportDataSnapshot,
    ReportDataSourceContext,
    ReportFilterItem,
    ReportFreshnessState,
    ReportReadingContext,
)


def _metric(
    canonical_measure: str,
    display_name: str,
    unit: str,
    format_name: str,
) -> MetricDefinition:
    return MetricDefinition(
        canonical_measure=canonical_measure,
        display_name=display_name,
        unit=unit,
        format=format_name,
        aggregation="semantic_measure",
        semantic_source=f"Sales[{canonical_measure}]",
        tax_basis=MetricDefinitionFacet.unknown(),
        comparison_basis=MetricDefinitionFacet.unknown(),
        definition_source="registry",
    )


SALES_METRIC_DEFINITIONS: Mapping[str, MetricDefinition] = MappingProxyType({
    "total_sales": _metric("Total Sales", "总销售额", "currency", "currency"),
    "total_quantity": _metric("Total Quantity", "总销量", "count", "number"),
    "total_orders": _metric("Total Orders", "总订单数", "count", "number"),
    "average_order_value": _metric(
        "Average Order Value", "平均订单金额", "currency", "currency"
    ),
})


class ReportReadingContextError(ValueError):
    pass


class ReportScopeContextBuilder:
    """Project one common scope only after VerifiedFactSet proves each plan."""

    def build(
        self,
        plans: Mapping[str, CanonicalQueryPlan],
        fact_sets: Mapping[str, VerifiedFactSet],
    ) -> tuple[ReportAnalysisPeriod, ActiveFilterContext]:
        if not plans or set(plans) != set(fact_sets):
            raise ReportReadingContextError("report_scope_provenance_incomplete")

        signatures: list[tuple[str, str]] = []
        for key, plan in plans.items():
            facts = fact_sets[key]
            if facts.semantic_model_key != plan.semantic_model_key:
                raise ReportReadingContextError("report_scope_model_mismatch")
            plan_semantics = plan.model_dump(mode="json")
            if any(
                item.provenance.plan_semantics != plan_semantics
                for item in facts.facts
            ):
                raise ReportReadingContextError("report_scope_fact_plan_mismatch")
            expected_filters = [item.model_dump(mode="json") for item in plan.filters]
            actual_filters = [
                item.value for item in facts.by_type(FactType.APPLIED_FILTER)
            ]
            if actual_filters != expected_filters:
                raise ReportReadingContextError("report_scope_filter_evidence_mismatch")
            actual_times = [
                item.value for item in facts.by_type(FactType.APPLIED_TIME_RANGE)
            ]
            expected_times = (
                []
                if plan.time_range is None
                else [plan.time_range.model_dump(mode="json")]
            )
            if actual_times != expected_times:
                raise ReportReadingContextError("report_scope_time_evidence_mismatch")
            signatures.append(
                (
                    repr(expected_times),
                    repr(expected_filters),
                )
            )
        if len(set(signatures)) != 1:
            raise ReportReadingContextError("report_scope_not_common_across_queries")

        first = next(iter(plans.values()))
        if first.time_range is None:
            period = ReportAnalysisPeriod(
                state=AnalysisPeriodState.ALL_AVAILABLE_DATA,
                display_text="全部可用数据",
            )
        else:
            period = ReportAnalysisPeriod(
                state=AnalysisPeriodState.BOUNDED,
                start_date=first.time_range.start_date,
                end_date=first.time_range.end_date,
                display_text=(
                    f"{first.time_range.start_date.isoformat()} 至 "
                    f"{first.time_range.end_date.isoformat()}"
                ),
            )

        filter_items: list[ReportFilterItem] = []
        for item in first.filters:
            values = item.value if isinstance(item.value, (list, tuple)) else (item.value,)
            rendered = "、".join(str(value) for value in values)
            filter_items.append(
                ReportFilterItem(
                    field=item.field,
                    operator=item.operator.value,
                    values=tuple(values),
                    display_text=f"{item.field} {item.operator.value} {rendered}",
                )
            )
        if not filter_items:
            filters = ActiveFilterContext(
                state=ActiveFilterState.NO_ADDITIONAL_FILTERS,
                display_text="无额外筛选",
            )
        else:
            filters = ActiveFilterContext(
                state=ActiveFilterState.APPLIED,
                items=tuple(filter_items),
                display_text="；".join(item.display_text for item in filter_items),
            )
        return period, filters

    def build_observed_coverage(
        self,
        plans: Mapping[str, CanonicalQueryPlan],
        fact_sets: Mapping[str, VerifiedFactSet],
    ) -> ObservedDataCoverage:
        if not plans or set(plans) != set(fact_sets):
            raise ReportReadingContextError("report_scope_provenance_incomplete")
        time_scoped = [
            fact_sets[key].observed_data_coverage
            for key, plan in plans.items()
            if plan.time_range is not None
        ]
        if not time_scoped:
            return ObservedDataCoverage(
                status=ObservedCoverageStatus.NOT_APPLICABLE
            )
        # This is a report-wide statement.  One monthly series cannot prove
        # that separate scalar/grouped queries observed the same coverage.
        # Preserve the strongest safe answer instead of promoting a single
        # query's FULL/PARTIAL evidence over UNKNOWN or EMPTY siblings.
        if any(
            item.status is ObservedCoverageStatus.UNKNOWN
            for item in time_scoped
        ):
            return ObservedDataCoverage(status=ObservedCoverageStatus.UNKNOWN)
        if any(
            item.status is ObservedCoverageStatus.EMPTY
            for item in time_scoped
        ):
            if all(
                item.status is ObservedCoverageStatus.EMPTY
                for item in time_scoped
            ):
                return ObservedDataCoverage(status=ObservedCoverageStatus.EMPTY)
            return ObservedDataCoverage(status=ObservedCoverageStatus.UNKNOWN)
        bounded = [
            item for item in time_scoped
            if item.status in {
                ObservedCoverageStatus.FULL,
                ObservedCoverageStatus.PARTIAL,
            }
        ]
        signatures = {
            (item.start_date, item.end_date, item.grain)
            for item in bounded
        }
        if len(signatures) == 1:
            representative = bounded[0]
            if any(
                item.status is ObservedCoverageStatus.PARTIAL
                for item in bounded
            ):
                return representative.model_copy(update={
                    "status": ObservedCoverageStatus.PARTIAL,
                })
            return representative
        if len(signatures) > 1:
            return ObservedDataCoverage(status=ObservedCoverageStatus.UNKNOWN)
        return ObservedDataCoverage(status=ObservedCoverageStatus.UNKNOWN)


class ReportDataSnapshotBuilder:
    """Bind current QueryResult/VerifiedFactSet provenance without freshness guesses."""

    def build(
        self,
        *,
        semantic_model_identity: str,
        schema_fingerprint: str,
        query_results: Mapping[str, QueryResult],
        verified_fact_sets: Mapping[str, VerifiedFactSet],
        source_kind: ReportDataSourceKind,
        semantic_model_display_name: str | None = None,
        source_display_name: str | None = None,
        queried_at: datetime,
        snapshot_at: datetime,
        data_updated_at: datetime | None = None,
    ) -> ReportDataSnapshot:
        if not query_results or set(query_results) != set(verified_fact_sets):
            raise ReportReadingContextError("report_snapshot_provenance_incomplete")
        source_modes = {item.source_mode for item in query_results.values()}
        if len(source_modes) != 1:
            raise ReportReadingContextError("report_snapshot_source_mode_mixed")
        for key, result in query_results.items():
            facts = verified_fact_sets[key]
            if (
                facts.result_id != result.result_id
                or facts.semantic_model_key != result.semantic_model_key
                or facts.source_mode != result.source_mode
                or result.semantic_model_key != semantic_model_identity
            ):
                raise ReportReadingContextError("report_snapshot_fact_binding_mismatch")
        return ReportDataSnapshot(
            semantic_model_identity=semantic_model_identity,
            semantic_model_display_name=semantic_model_display_name,
            schema_fingerprint=schema_fingerprint,
            query_result_ids=tuple(
                item.result_id for item in query_results.values()
            ),
            verified_fact_set_ids=tuple(
                verified_fact_sets[key].fact_set_id for key in query_results
            ),
            source_mode=next(iter(source_modes)),
            source_kind=source_kind,
            source_display_name=source_display_name,
            data_updated_at=data_updated_at,
            queried_at=queried_at,
            snapshot_at=snapshot_at,
        )


class ReportReadingContextBuilder:
    """Build context only from explicit scope, registry definitions, and snapshot."""

    def __init__(
        self,
        metric_definitions: Mapping[str, MetricDefinition] = SALES_METRIC_DEFINITIONS,
    ) -> None:
        self._metric_definitions = MappingProxyType(dict(metric_definitions))

    def build(
        self,
        *,
        report_title: str,
        analysis_period: ReportAnalysisPeriod,
        active_filters: ActiveFilterContext,
        metric_definition_keys: tuple[str, ...],
        exception_assessment: ExceptionAssessment,
        snapshot: ReportDataSnapshot,
        generated_at: datetime,
        observed_data_coverage: ObservedDataCoverage | None = None,
        data_availability: tuple[DataAvailabilityContext, ...] = (),
    ) -> ReportReadingContext:
        if not metric_definition_keys:
            raise ReportReadingContextError("report_metric_definitions_required")
        try:
            definitions = tuple(
                self._metric_definitions[key] for key in metric_definition_keys
            )
        except KeyError as exc:
            raise ReportReadingContextError(
                f"report_metric_definition_unknown:{exc.args[0]}"
            ) from exc

        if snapshot.data_updated_at is None:
            freshness = ReportDataFreshness.unknown()
        else:
            freshness = ReportDataFreshness(
                state=ReportFreshnessState.KNOWN,
                data_updated_at=snapshot.data_updated_at,
                display_text=(
                    "数据更新时间：" + snapshot.data_updated_at.isoformat()
                ),
                evidence_source="runtime_refresh_metadata",
            )
        return ReportReadingContext(
            report_title=report_title,
            analysis_period=analysis_period,
            active_filters=active_filters,
            metric_definitions=definitions,
            exception_assessment=exception_assessment,
            semantic_model=snapshot.semantic_model_identity,
            data_source=ReportDataSourceContext(
                kind=snapshot.source_kind,
                source_mode=snapshot.source_mode,
                display_name=(
                    snapshot.source_display_name
                    or _source_display_name(
                        snapshot.source_kind,
                        snapshot.source_mode,
                    )
                ),
            ),
            data_freshness=freshness,
            observed_data_coverage=(
                observed_data_coverage
                or ObservedDataCoverage(
                    status=(
                        ObservedCoverageStatus.UNKNOWN
                        if analysis_period.state is AnalysisPeriodState.BOUNDED
                        else ObservedCoverageStatus.NOT_APPLICABLE
                    )
                )
            ),
            data_availability=data_availability,
            generated_at=generated_at,
        )


def _source_display_name(
    kind: ReportDataSourceKind,
    source_mode: str,
) -> str:
    base = {
        ReportDataSourceKind.LOCAL_MCP: "Power BI Desktop",
        ReportDataSourceKind.REMOTE_MCP: "远程 Power BI",
        ReportDataSourceKind.TEST_FIXTURE: "测试数据",
    }[kind]
    suffix = "实时查询" if source_mode == "real" else "验证模式"
    return f"{base} · {suffix}"
