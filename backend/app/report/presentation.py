"""Presentation-only projection for fixed professional reports.

Canonical identities, enums, timestamps and facts remain on ReportSpec and
ReportDataSnapshot.  This module only produces deterministic display text.
"""

from __future__ import annotations

from backend.app.presentation.messages import message,display_resource
from backend.app.presentation.locale import current_locale
from backend.app.presentation.formatter import PresentationFormatter,PresentationFormatKind

from datetime import datetime
import re
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, computed_field

from backend.app.schemas.data_contracts import ReportSpec
from backend.app.schemas.factual_context import (
    DataHorizonStatus,
    ObservedCoverageStatus,
)
from backend.app.schemas.report_context import (
    ExceptionAssessmentState,
    MetricDefinitionStatus,
    ReportDataSourceKind,
    ReportFreshnessState,
)


DEFAULT_REPORT_DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")


class PresentedMetricDefinition(BaseModel):
    canonical_measure: str
    canonical_source: str
    display_name: str
    aggregation_display: str
    unit_display: str
    tax_basis_display: str
    comparison_basis_display: str

    model_config = ConfigDict(frozen=True)


class ReportPresentationProjection(BaseModel):
    model_display_name: str
    source_display_name: str
    analysis_period_display: str
    filter_display: str
    freshness_display: str
    observed_coverage_display: str
    data_availability_display: str
    exception_display: str
    generated_at_display: str
    queried_at_display: str
    snapshot_at_display: str
    metric_summary: str
    metric_definitions: tuple[PresentedMetricDefinition, ...]
    canonical_model_identity: str
    canonical_source_kind: ReportDataSourceKind
    canonical_source_mode: str
    canonical_generated_at: str
    canonical_queried_at: str
    canonical_snapshot_at: str
    schema_fingerprint: str

    model_config = ConfigDict(frozen=True)

    @computed_field
    @property
    def main_text(self) -> str:
        parts = (
            self.model_display_name,
            self.source_display_name,
            self.analysis_period_display,
            self.filter_display,
            self.freshness_display,
            self.observed_coverage_display,
            self.data_availability_display,
            self.exception_display,
            self.generated_at_display,
            self.metric_summary,
            *(item.display_name for item in self.metric_definitions),
            *(item.aggregation_display for item in self.metric_definitions),
            *(item.unit_display for item in self.metric_definitions),
            *(item.tax_basis_display for item in self.metric_definitions),
            *(item.comparison_basis_display for item in self.metric_definitions),
        )
        return " | ".join(parts)

    def metric_label(self, canonical_measure: str) -> str:
        for item in self.metric_definitions:
            if item.canonical_measure == canonical_measure:
                return item.display_name
        return message('display.business_measure')

    def metric_unit(self, canonical_measure: str) -> str:
        for item in self.metric_definitions:
            if item.canonical_measure == canonical_measure:
                return item.unit_display
        return message('display.value')


class ProfessionalReportPresenter:
    """Map a validated complex ReportSpec to business-friendly text only."""

    _OPAQUE_PREFIXES = ("local_desktop:", "local_mcp:", "remote_mcp:", "fabric_iq:")
    _LONG_HEX = re.compile(r"[0-9a-f]{24,}", re.IGNORECASE)
    _FIELD_LABELS = {
        "Region": 'display.region',
        "Category": 'display.category',
        "Product": 'display.product',
        "Customer": 'display.customer',
        "YearMonth": 'display.month',
    }
    _OPERATOR_LABELS = {
        "eq": 'display.equals',
        "in": 'display.is_in',
        "in_set": 'display.is_in',
    }

    def project(self, report: ReportSpec) -> ReportPresentationProjection:
        context = report.reading_context
        snapshot = report.data_snapshot
        if context is None or snapshot is None:
            raise ValueError("professional_report_context_required")

        metrics = tuple(self._metric(item) for item in context.metric_definitions)
        unknown_tax = all(item.tax_basis.status is MetricDefinitionStatus.UNKNOWN
                          for item in context.metric_definitions)
        unknown_comparison = all(
            item.comparison_basis.status is MetricDefinitionStatus.UNKNOWN
            for item in context.metric_definitions
        )
        summary = message('display.p_core_measures_bound_to_power_bi', p0=len(metrics))
        if unknown_tax:
            summary += message('display.tax_basis_not_declared')
        if unknown_comparison:
            summary += message('display.comparison_basis_not_set')

        return ReportPresentationProjection(
            model_display_name=self._model_display_name(snapshot),
            source_display_name=self._source_display_name(snapshot),
            analysis_period_display=(message("report.period_range", start=context.analysis_period.start_date.isoformat(),
                end=context.analysis_period.end_date.isoformat()) if context.analysis_period.start_date is not None
                else message("report.all_available")),
            filter_display=self._filter_display(context.active_filters),
            freshness_display=(
                message('display.unavailable')
                if context.data_freshness.state is ReportFreshnessState.UNKNOWN
                else self._format_datetime(context.data_freshness.data_updated_at)
            ),
            observed_coverage_display=self._coverage_display(
                context.observed_data_coverage
            ),
            data_availability_display=self._availability_display(
                context.data_availability,
                context.metric_definitions,
            ),
            exception_display=(
                message('display.no_verified_exception_benchmark')
                if context.exception_assessment.state
                is ExceptionAssessmentState.CANNOT_DETERMINE
                else context.exception_assessment.message
            ),
            generated_at_display=self._format_datetime(context.generated_at),
            queried_at_display=self._format_datetime(snapshot.queried_at),
            snapshot_at_display=self._format_datetime(snapshot.snapshot_at),
            metric_summary=summary,
            metric_definitions=metrics,
            canonical_model_identity=snapshot.semantic_model_identity,
            canonical_source_kind=snapshot.source_kind,
            canonical_source_mode=snapshot.source_mode,
            canonical_generated_at=context.generated_at.isoformat(),
            canonical_queried_at=snapshot.queried_at.isoformat(),
            canonical_snapshot_at=snapshot.snapshot_at.isoformat(),
            schema_fingerprint=snapshot.schema_fingerprint,
        )

    @staticmethod
    def _availability_display(data_availability, metric_definitions) -> str:
        if not data_availability:
            return message('display.cannot_determine')
        labels = {
            item.canonical_measure: display_resource(item.display_name)
            for item in metric_definitions
        }
        rendered: list[str] = []
        for item in data_availability:
            horizon = item.available_data_horizon
            if horizon is None or horizon.status is DataHorizonStatus.UNKNOWN:
                continue
            label = labels.get(horizon.measure, horizon.measure)
            if horizon.status is DataHorizonStatus.EMPTY:
                rendered.append(message('display.no_observable_data_for_p', p0=label))
            elif horizon.latest_period is not None:
                rendered.append(
                    message('display.p_observable_through_p_p', p0=label, p1=horizon.latest_period.year, p2=horizon.latest_period.month)
                )
        return "；".join(rendered) if rendered else message('display.cannot_determine')

    @classmethod
    def _model_display_name(cls, snapshot) -> str:
        candidate = (snapshot.semantic_model_display_name or "").strip()
        if (
            candidate
            and not candidate.casefold().startswith(cls._OPAQUE_PREFIXES)
            and cls._LONG_HEX.search(candidate) is None
            and candidate != snapshot.semantic_model_identity
        ):
            return candidate
        if snapshot.source_kind is ReportDataSourceKind.LOCAL_MCP:
            return message('display.current_power_bi_desktop_model')
        if snapshot.source_kind is ReportDataSourceKind.REMOTE_MCP:
            return message('display.current_power_bi_semantic_model')
        if snapshot.source_kind is ReportDataSourceKind.FABRIC_IQ:
            return message('display.current_power_bi_semantic_model')
        return message('display.report_validation_model')

    @staticmethod
    def _source_display_name(snapshot) -> str:
        base = (snapshot.source_display_name or "").strip() or {
            ReportDataSourceKind.LOCAL_MCP: "Power BI Desktop",
            ReportDataSourceKind.FABRIC_IQ: "Fabric IQ",
            ReportDataSourceKind.REMOTE_MCP: message('display.remote_power_bi'),
            ReportDataSourceKind.TEST_FIXTURE: message('display.test_data'),
        }[snapshot.source_kind]
        suffix = message('display.live_query') if snapshot.source_mode == "real" else message('display.validation_mode')
        return base if suffix in base else f"{base} · {suffix}"

    @classmethod
    def _filter_display(cls, filters) -> str:
        if not filters.items:
            return display_resource(filters.display_text)
        rendered: list[str] = []
        for item in filters.items:
            field = message(cls._FIELD_LABELS[item.field]) if item.field in cls._FIELD_LABELS else item.field
            operator = message(cls._OPERATOR_LABELS[item.operator]) if item.operator in cls._OPERATOR_LABELS else item.operator
            rendered.append(
                message("report.filter_item",field=field,operator=operator,values=message("common.list_separator").join(str(value) for value in item.values))
            )
        return "；".join(rendered)

    @staticmethod
    def _coverage_display(coverage) -> str:
        if coverage.status is ObservedCoverageStatus.EMPTY:
            return message('display.no_data_returned')
        if coverage.status is ObservedCoverageStatus.UNKNOWN:
            return message('display.unknown')
        if coverage.status is ObservedCoverageStatus.NOT_APPLICABLE:
            return message('display.not_applicable')
        assert coverage.start_date is not None and coverage.end_date is not None
        state = message('display.complete') if coverage.status is ObservedCoverageStatus.FULL else message('display.partial')
        return (
            message('display.p_p_p_p_p', p0=coverage.start_date.year, p1=coverage.start_date.month, p2=coverage.end_date.year, p3=coverage.end_date.month, p4=state)
        )

    @staticmethod
    def _metric(definition) -> PresentedMetricDefinition:
        return PresentedMetricDefinition(
            canonical_measure=definition.canonical_measure,
            canonical_source=definition.semantic_source,
            display_name=display_resource(definition.display_name),
            aggregation_display={
                "semantic_measure": message('display.power_bi_measure'),
            }.get(definition.aggregation, message('display.model_defined_measure')),
            unit_display={
                "currency": message('display.amount'),
                "count": message('display.count'),
            }.get(definition.unit, message('display.value')),
            tax_basis_display=(
                message('display.not_declared')
                if definition.tax_basis.status is MetricDefinitionStatus.UNKNOWN
                else str(definition.tax_basis.value)
            ),
            comparison_basis_display=(
                message('display.not_set')
                if definition.comparison_basis.status
                is MetricDefinitionStatus.UNKNOWN
                else str(definition.comparison_basis.value)
            ),
        )

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return message('display.unavailable')
        if value.tzinfo is None or value.utcoffset() is None:
            return message('display.p_timezone_not_declared', p0=value.strftime('%Y-%m-%d %H:%M'))
        local_value = value.astimezone(DEFAULT_REPORT_DISPLAY_TIMEZONE)
        return local_value.strftime("%Y-%m-%d %H:%M") + message('display.beijing_time')
