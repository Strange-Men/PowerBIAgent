"""Immutable platform contracts for complex-report reading context.

These schemas contain no query, rendering, LLM, or transport capability.  They
make the information a reader must see explicit and keep data freshness
separate from artifact generation time.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportTemplateTier(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class AnalysisPeriodState(str, Enum):
    BOUNDED = "bounded"
    ALL_AVAILABLE_DATA = "all_available_data"


class ActiveFilterState(str, Enum):
    NO_ADDITIONAL_FILTERS = "no_additional_filters"
    APPLIED = "applied"


class MetricDefinitionStatus(str, Enum):
    DECLARED = "declared"
    UNKNOWN = "unknown"


class ExceptionAssessmentState(str, Enum):
    EVALUATED = "evaluated"
    CANNOT_DETERMINE = "cannot_determine"


class ReportFreshnessState(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class ReportDataSourceKind(str, Enum):
    TEST_FIXTURE = "test_fixture"
    LOCAL_MCP = "local_mcp"
    # Reserved contract value only.  M5.10 does not implement transport,
    # authentication, polling, or any Remote MCP request schema.
    REMOTE_MCP = "remote_mcp"


class ReportAnalysisPeriod(BaseModel):
    state: AnalysisPeriodState
    start_date: date | None = None
    end_date: date | None = None
    display_text: str = Field(..., min_length=1)
    authority: Literal["canonical_verified_scope"] = "canonical_verified_scope"

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_period(self) -> "ReportAnalysisPeriod":
        if self.state is AnalysisPeriodState.BOUNDED:
            if self.start_date is None or self.end_date is None:
                raise ValueError("report_analysis_period_bounds_required")
            if self.end_date < self.start_date:
                raise ValueError("report_analysis_period_bounds_invalid")
        elif self.start_date is not None or self.end_date is not None:
            raise ValueError("report_all_data_period_must_not_have_bounds")
        return self


class ReportFilterItem(BaseModel):
    field: str = Field(..., min_length=1)
    operator: str = Field(..., min_length=1)
    values: tuple[Any, ...] = Field(..., min_length=1)
    display_text: str = Field(..., min_length=1)
    authority: Literal["canonical_verified_scope"] = "canonical_verified_scope"

    model_config = ConfigDict(frozen=True, extra="forbid")


class ActiveFilterContext(BaseModel):
    state: ActiveFilterState
    items: tuple[ReportFilterItem, ...] = ()
    display_text: str = Field(..., min_length=1)
    authority: Literal["canonical_verified_scope"] = "canonical_verified_scope"

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_filter_state(self) -> "ActiveFilterContext":
        if self.state is ActiveFilterState.NO_ADDITIONAL_FILTERS:
            if self.items:
                raise ValueError("report_no_filter_state_has_items")
            if self.display_text != "无额外筛选":
                raise ValueError("report_no_filter_state_text_invalid")
        elif not self.items:
            raise ValueError("report_applied_filter_items_required")
        return self


class MetricDefinitionFacet(BaseModel):
    status: MetricDefinitionStatus
    value: str | None = None
    source: Literal["registry", "runtime_metadata", "exact_override", "unknown"] = (
        "unknown"
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def unknown(cls) -> "MetricDefinitionFacet":
        return cls(status=MetricDefinitionStatus.UNKNOWN)

    @model_validator(mode="after")
    def validate_status(self) -> "MetricDefinitionFacet":
        if self.status is MetricDefinitionStatus.UNKNOWN:
            if self.value is not None or self.source != "unknown":
                raise ValueError("metric_definition_unknown_must_stay_unknown")
        elif not self.value or self.source == "unknown":
            raise ValueError("metric_definition_declared_value_and_source_required")
        return self


class MetricDefinition(BaseModel):
    canonical_measure: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1)
    format: str = Field(..., min_length=1)
    aggregation: str = Field(..., min_length=1)
    semantic_source: str = Field(..., min_length=1)
    tax_basis: MetricDefinitionFacet
    comparison_basis: MetricDefinitionFacet
    definition_source: Literal["registry", "runtime_metadata", "exact_override"]

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExceptionAssessment(BaseModel):
    state: ExceptionAssessmentState
    message: str = Field(..., min_length=1)
    rule_id: str | None = None
    evidence_fact_ids: tuple[str, ...] = ()
    authority: Literal["deterministic_rule_registry"] = (
        "deterministic_rule_registry"
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def cannot_determine(cls) -> "ExceptionAssessment":
        return cls(
            state=ExceptionAssessmentState.CANNOT_DETERMINE,
            message="当前模型未提供可验证的目标、预测或异常判断基准",
        )

    @model_validator(mode="after")
    def validate_assessment(self) -> "ExceptionAssessment":
        if self.state is ExceptionAssessmentState.EVALUATED:
            if not self.rule_id or not self.evidence_fact_ids:
                raise ValueError("report_exception_evidence_required")
        elif self.rule_id is not None or self.evidence_fact_ids:
            raise ValueError("report_exception_unavailable_cannot_have_evidence")
        return self


class ReportDataFreshness(BaseModel):
    state: ReportFreshnessState
    data_updated_at: datetime | None = None
    display_text: str = Field(..., min_length=1)
    evidence_source: Literal["runtime_refresh_metadata", "unknown"]

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def unknown(cls) -> "ReportDataFreshness":
        return cls(
            state=ReportFreshnessState.UNKNOWN,
            data_updated_at=None,
            display_text="数据更新时间：模型未提供",
            evidence_source="unknown",
        )

    @model_validator(mode="after")
    def validate_freshness(self) -> "ReportDataFreshness":
        if self.state is ReportFreshnessState.KNOWN:
            if self.data_updated_at is None:
                raise ValueError("report_data_updated_at_required")
            if self.evidence_source != "runtime_refresh_metadata":
                raise ValueError("report_data_freshness_evidence_invalid")
        elif self.data_updated_at is not None or self.evidence_source != "unknown":
            raise ValueError("report_unknown_freshness_must_not_claim_timestamp")
        return self


class ReportDataSourceContext(BaseModel):
    kind: ReportDataSourceKind
    source_mode: Literal["mock", "real"]
    display_name: str = Field(..., min_length=1)

    model_config = ConfigDict(frozen=True, extra="forbid")


class ReportDataSnapshot(BaseModel):
    """Immutable fact/provenance snapshot, independent of artifact creation."""

    semantic_model_identity: str = Field(..., min_length=1)
    schema_fingerprint: str = Field(..., min_length=1)
    query_result_ids: tuple[str, ...] = Field(..., min_length=1)
    verified_fact_set_ids: tuple[str, ...] = Field(..., min_length=1)
    source_mode: Literal["mock", "real"]
    source_kind: ReportDataSourceKind
    data_updated_at: datetime | None = None
    queried_at: datetime
    snapshot_at: datetime

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ReportDataSnapshot":
        if len(self.query_result_ids) != len(self.verified_fact_set_ids):
            raise ValueError("report_snapshot_provenance_incomplete")
        if len(set(self.query_result_ids)) != len(self.query_result_ids):
            raise ValueError("report_snapshot_query_result_ids_duplicate")
        if len(set(self.verified_fact_set_ids)) != len(self.verified_fact_set_ids):
            raise ValueError("report_snapshot_fact_set_ids_duplicate")
        if (
            self.source_mode == "mock"
            and self.source_kind is not ReportDataSourceKind.TEST_FIXTURE
        ):
            raise ValueError("report_snapshot_mock_source_kind_invalid")
        if (
            self.source_mode == "real"
            and self.source_kind is ReportDataSourceKind.TEST_FIXTURE
        ):
            raise ValueError("report_snapshot_real_source_kind_invalid")
        return self


class ReportReadingContext(BaseModel):
    report_title: str = Field(..., min_length=1)
    analysis_period: ReportAnalysisPeriod
    active_filters: ActiveFilterContext
    metric_definitions: tuple[MetricDefinition, ...] = Field(..., min_length=1)
    exception_assessment: ExceptionAssessment
    semantic_model: str = Field(..., min_length=1)
    data_source: ReportDataSourceContext
    data_freshness: ReportDataFreshness
    generated_at: datetime

    model_config = ConfigDict(frozen=True, extra="forbid")
