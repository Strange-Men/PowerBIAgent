"""Presentation-only projection for fixed professional reports.

Canonical identities, enums, timestamps and facts remain on ReportSpec and
ReportDataSnapshot.  This module only produces deterministic display text.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re

from pydantic import BaseModel, ConfigDict, computed_field

from backend.app.schemas.data_contracts import ReportSpec
from backend.app.schemas.report_context import (
    ExceptionAssessmentState,
    MetricDefinitionStatus,
    ReportDataSourceKind,
    ReportFreshnessState,
)


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
        return "业务指标"

    def metric_unit(self, canonical_measure: str) -> str:
        for item in self.metric_definitions:
            if item.canonical_measure == canonical_measure:
                return item.unit_display
        return "数值"


class ProfessionalReportPresenter:
    """Map a validated complex ReportSpec to business-friendly text only."""

    _OPAQUE_PREFIXES = ("local_desktop:", "local_mcp:", "remote_mcp:")
    _LONG_HEX = re.compile(r"[0-9a-f]{24,}", re.IGNORECASE)
    _FIELD_LABELS = {
        "Region": "区域",
        "Category": "品类",
        "Product": "产品",
        "Customer": "客户",
        "YearMonth": "月份",
    }
    _OPERATOR_LABELS = {
        "eq": "等于",
        "in": "属于",
        "in_set": "属于",
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
        summary = f"{len(metrics)} 项核心指标已绑定 Power BI 度量值"
        if unknown_tax:
            summary += " · 税务口径：未声明"
        if unknown_comparison:
            summary += " · 比较基准：未设置"

        return ReportPresentationProjection(
            model_display_name=self._model_display_name(snapshot),
            source_display_name=self._source_display_name(snapshot),
            analysis_period_display=context.analysis_period.display_text,
            filter_display=self._filter_display(context.active_filters),
            freshness_display=(
                "暂不可获取"
                if context.data_freshness.state is ReportFreshnessState.UNKNOWN
                else self._format_datetime(context.data_freshness.data_updated_at)
            ),
            exception_display=(
                "暂无可验证异常基准"
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
            return "当前 Power BI Desktop 模型"
        if snapshot.source_kind is ReportDataSourceKind.REMOTE_MCP:
            return "当前 Power BI 语义模型"
        return "报表验证模型"

    @staticmethod
    def _source_display_name(snapshot) -> str:
        base = (snapshot.source_display_name or "").strip() or {
            ReportDataSourceKind.LOCAL_MCP: "Power BI Desktop",
            ReportDataSourceKind.REMOTE_MCP: "远程 Power BI",
            ReportDataSourceKind.TEST_FIXTURE: "测试数据",
        }[snapshot.source_kind]
        suffix = "实时查询" if snapshot.source_mode == "real" else "验证模式"
        return base if suffix in base else f"{base} · {suffix}"

    @classmethod
    def _filter_display(cls, filters) -> str:
        if not filters.items:
            return filters.display_text
        rendered: list[str] = []
        for item in filters.items:
            field = cls._FIELD_LABELS.get(item.field, item.field)
            operator = cls._OPERATOR_LABELS.get(item.operator, item.operator)
            rendered.append(
                f"{field}{operator}{'、'.join(str(value) for value in item.values)}"
            )
        return "；".join(rendered)

    @staticmethod
    def _metric(definition) -> PresentedMetricDefinition:
        return PresentedMetricDefinition(
            canonical_measure=definition.canonical_measure,
            canonical_source=definition.semantic_source,
            display_name=definition.display_name,
            aggregation_display={
                "semantic_measure": "Power BI 度量值",
            }.get(definition.aggregation, "模型定义指标"),
            unit_display={
                "currency": "金额",
                "count": "数量",
            }.get(definition.unit, "数值"),
            tax_basis_display=(
                "未声明"
                if definition.tax_basis.status is MetricDefinitionStatus.UNKNOWN
                else str(definition.tax_basis.value)
            ),
            comparison_basis_display=(
                "未设置"
                if definition.comparison_basis.status
                is MetricDefinitionStatus.UNKNOWN
                else str(definition.comparison_basis.value)
            ),
        )

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "暂不可获取"
        if value.tzinfo is None or value.utcoffset() is None:
            return value.strftime("%Y-%m-%d %H:%M（时区未声明）")
        utc_value = value.astimezone(timezone.utc)
        return utc_value.strftime("%Y-%m-%d %H:%M UTC")
