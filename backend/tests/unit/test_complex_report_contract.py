"""M5.10 complex-report platform and professional-template governance."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.facts import VerifiedFactSetBuilder
from backend.app.report.base import ReportRenderer
from backend.app.report.contracts import (
    SALES_EXECUTIVE_REPORT_CONTRACT,
    SALES_QUERY_REQUIREMENTS,
    SALES_REPORT_CONTRACT,
    ReportAvailabilityStatus,
    ReportContractValidator,
)
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.reading_context import (
    ReportReadingContextBuilder,
    ReportScopeContextBuilder,
    SALES_METRIC_DEFINITIONS,
)
from backend.app.report.registry import (
    DEFAULT_REPORT_TEMPLATE_REGISTRY,
    ReportRendererDispatcher,
    ReportRendererRegistry,
    ReportTemplateAvailability,
    ReportTemplateDescriptor,
    ReportTemplateRegistry,
    ReportTemplateUnavailableError,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    FilterOperator,
    KPISpec,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)
from backend.app.schemas.report_context import (
    ActiveFilterContext,
    ActiveFilterState,
    AnalysisPeriodState,
    ExceptionAssessment,
    ExceptionAssessmentState,
    MetricDefinition,
    MetricDefinitionFacet,
    MetricDefinitionStatus,
    ReportAnalysisPeriod,
    ReportDataSnapshot,
    ReportDataSourceKind,
    ReportFreshnessState,
    ReportReadingContext,
    ReportTemplateTier,
)


NOW = datetime(2026, 9, 11, 8, 30, tzinfo=timezone.utc)
UPDATED = datetime(2026, 9, 11, 6, 0, tzinfo=timezone.utc)


class _RecordingRenderer(ReportRenderer):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def supported_templates(self) -> list[str]:
        return ["test"]

    async def render(self, report: ReportSpec) -> str:
        self.calls += 1
        return "<!DOCTYPE html><html><body>ok</body></html>"


def _snapshot(*, data_updated_at: datetime | None = UPDATED) -> ReportDataSnapshot:
    return ReportDataSnapshot(
        semantic_model_identity="local_desktop:model-a",
        schema_fingerprint="a" * 64,
        query_result_ids=("result-1",),
        verified_fact_set_ids=("facts-1",),
        source_mode="real",
        source_kind=ReportDataSourceKind.LOCAL_MCP,
        data_updated_at=data_updated_at,
        queried_at=NOW,
        snapshot_at=NOW,
    )


def _period() -> ReportAnalysisPeriod:
    return ReportAnalysisPeriod(
        state=AnalysisPeriodState.BOUNDED,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
        display_text="2026-01-01 至 2026-06-30",
    )


def _filters() -> ActiveFilterContext:
    return ActiveFilterContext(
        state=ActiveFilterState.NO_ADDITIONAL_FILTERS,
        display_text="无额外筛选",
    )


def _reading_context(
    *, snapshot: ReportDataSnapshot | None = None
) -> ReportReadingContext:
    return ReportReadingContextBuilder().build(
        report_title="销售经营分析报表",
        analysis_period=_period(),
        active_filters=_filters(),
        metric_definition_keys=("total_sales",),
        exception_assessment=ExceptionAssessment.cannot_determine(),
        snapshot=snapshot or _snapshot(),
        generated_at=NOW,
    )


def test_template_governance_registers_simple_and_unavailable_complex_identity():
    simple = DEFAULT_REPORT_TEMPLATE_REGISTRY.get("sales_report")
    executive = DEFAULT_REPORT_TEMPLATE_REGISTRY.get("sales_executive_report")

    assert simple is not None
    assert simple.tier is ReportTemplateTier.SIMPLE
    assert simple.availability is ReportTemplateAvailability.AVAILABLE
    assert executive is not None
    assert executive.display_name == "专业销售经营分析模板"
    assert executive.tier is ReportTemplateTier.COMPLEX
    assert executive.renderer_key == "executive_sales_report"
    assert executive.availability is ReportTemplateAvailability.UNAVAILABLE
    assert DEFAULT_REPORT_TEMPLATE_REGISTRY.available_keys == ("sales_report",)
    assert [
        item.template_key
        for item in DEFAULT_REPORT_TEMPLATE_REGISTRY.public_catalog().items
    ] == ["sales_report"]


def test_professional_contract_is_registered_but_cannot_build_a_production_plan():
    validation = ReportContractValidator().validate(
        "sales_executive_report",
        # Availability must fail before runtime schema is used.
        SemanticModelSchema(name="unused", key="unused", tables=[]),
    )
    assert validation.status is ReportAvailabilityStatus.TEMPLATE_NOT_AVAILABLE
    assert validation.available is False


def test_sales_contracts_share_one_requirement_authority_and_semantics():
    assert all(
        left is authority
        for left, authority in zip(
            SALES_REPORT_CONTRACT.query_requirements,
            SALES_QUERY_REQUIREMENTS,
            strict=True,
        )
    )
    assert all(
        right is authority
        for right, authority in zip(
            SALES_EXECUTIVE_REPORT_CONTRACT.query_requirements,
            SALES_QUERY_REQUIREMENTS,
            strict=True,
        )
    )
    by_key = {item.key: item for item in SALES_QUERY_REQUIREMENTS}
    assert {key: by_key[key] for key in (
        "total_sales", "monthly_sales", "sales_by_region", "top_products"
    )} == {
        key: next(
            item for item in SALES_EXECUTIVE_REPORT_CONTRACT.query_requirements
            if item.key == key
        )
        for key in ("total_sales", "monthly_sales", "sales_by_region", "top_products")
    }


@pytest.mark.asyncio
async def test_simple_template_does_not_require_complex_reading_context():
    renderer = _RecordingRenderer()
    dispatcher = ReportRendererDispatcher(
        template_registry=ReportTemplateRegistry((
            ReportTemplateDescriptor(
                template_key="simple",
                display_name="Simple",
                description="Simple",
                renderer_key="simple_renderer",
                availability=ReportTemplateAvailability.AVAILABLE,
                tier=ReportTemplateTier.SIMPLE,
            ),
        )),
        renderer_registry=ReportRendererRegistry((("simple_renderer", renderer),)),
    )

    await dispatcher.render(ReportSpec(title="Simple", template_key="simple"))
    assert renderer.calls == 1


@pytest.mark.asyncio
async def test_complex_template_missing_reading_context_fails_before_renderer():
    renderer = _RecordingRenderer()
    dispatcher = ReportRendererDispatcher(
        template_registry=ReportTemplateRegistry((
            ReportTemplateDescriptor(
                template_key="complex",
                display_name="Complex",
                description="Complex",
                renderer_key="complex_renderer",
                availability=ReportTemplateAvailability.AVAILABLE,
                tier=ReportTemplateTier.COMPLEX,
            ),
        )),
        renderer_registry=ReportRendererRegistry((("complex_renderer", renderer),)),
    )

    with pytest.raises(
        ReportTemplateUnavailableError,
        match="complex_report_reading_context_required",
    ):
        await dispatcher.render(ReportSpec(title="Complex", template_key="complex"))
    assert renderer.calls == 0


@pytest.mark.asyncio
async def test_coherent_complex_contract_reaches_only_its_registered_renderer():
    renderer = _RecordingRenderer()
    dispatcher = ReportRendererDispatcher(
        template_registry=ReportTemplateRegistry((
            ReportTemplateDescriptor(
                template_key="complex",
                display_name="Complex",
                description="Complex",
                renderer_key="complex_renderer",
                availability=ReportTemplateAvailability.AVAILABLE,
                tier=ReportTemplateTier.COMPLEX,
            ),
        )),
        renderer_registry=ReportRendererRegistry((("complex_renderer", renderer),)),
    )
    snapshot = _snapshot()
    context = _reading_context(snapshot=snapshot)
    report = ReportSpec(
        title=context.report_title,
        template_key="complex",
        generated_at=NOW,
        source_mode="real",
        semantic_model_key=snapshot.semantic_model_identity,
        schema_fingerprint=snapshot.schema_fingerprint,
        reading_context=context,
        data_snapshot=snapshot,
    )

    await dispatcher.render(report)
    assert renderer.calls == 1


@pytest.mark.asyncio
async def test_unavailable_executive_template_never_falls_back_to_simple_renderer():
    renderer = _RecordingRenderer()
    dispatcher = ReportRendererDispatcher(
        template_registry=DEFAULT_REPORT_TEMPLATE_REGISTRY,
        renderer_registry=ReportRendererRegistry((("simple_report", renderer),)),
    )

    with pytest.raises(ReportTemplateUnavailableError):
        await dispatcher.render(
            ReportSpec(title="Executive", template_key="sales_executive_report")
        )
    assert renderer.calls == 0


@pytest.mark.parametrize(
    "missing_field",
    [
        "report_title",
        "analysis_period",
        "active_filters",
        "metric_definitions",
        "exception_assessment",
        "semantic_model",
        "data_source",
        "data_freshness",
        "generated_at",
    ],
)
def test_reading_context_missing_required_field_fails_closed(missing_field: str):
    payload = _reading_context().model_dump()
    payload.pop(missing_field)
    with pytest.raises(ValidationError):
        ReportReadingContext.model_validate(payload)


def test_no_filter_scope_is_explicit_and_never_blank():
    context = _filters()
    assert context.state is ActiveFilterState.NO_ADDITIONAL_FILTERS
    assert context.items == ()
    assert context.display_text == "无额外筛选"
    with pytest.raises(ValidationError):
        ActiveFilterContext(
            state=ActiveFilterState.NO_ADDITIONAL_FILTERS,
            display_text="",
        )


def test_filter_and_time_context_are_projected_from_canonical_verified_scope():
    plan = CanonicalQueryPlan(
        normalized_question="verified scope",
        semantic_model_key="model-a",
        measures=["Total Sales"],
        filters=[StructuredFilter(
            field="Region",
            operator=FilterOperator.EQ,
            value="South",
        )],
        time_range=TimeRangeSpec(
            date_field="OrderDate",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            mode=TimeRangeMode.EXPLICIT_RANGE,
        ),
    )
    result = QueryResult(
        result_id="result-scope",
        semantic_model_key="model-a",
        columns=["[Total Sales]"],
        rows=[[100]],
        row_count=1,
        source_mode="real",
    )
    facts = VerifiedFactSetBuilder().build(plan, result)

    period, filters = ReportScopeContextBuilder().build(
        {"total_sales": plan}, {"total_sales": facts}
    )

    assert period.start_date == date(2026, 1, 1)
    assert period.end_date == date(2026, 6, 30)
    assert period.authority == "canonical_verified_scope"
    assert filters.state is ActiveFilterState.APPLIED
    assert filters.items[0].field == "Region"
    assert filters.items[0].values == ("South",)
    assert filters.items[0].authority == "canonical_verified_scope"


def test_generated_at_never_becomes_data_updated_at_and_unknown_stays_unknown():
    context = _reading_context(snapshot=_snapshot(data_updated_at=None))
    assert context.generated_at == NOW
    assert context.data_freshness.state is ReportFreshnessState.UNKNOWN
    assert context.data_freshness.data_updated_at is None
    assert context.data_freshness.display_text == "数据更新时间：模型未提供"


@pytest.mark.asyncio
async def test_simple_renderer_labels_artifact_clock_as_generated_not_refresh_time():
    html = await SalesReportRenderer().render(ReportSpec(
        title="销售分析报表",
        template_key="sales_report",
        kpis=[KPISpec(
            name="总销售额", value=100, format="currency", field="Total Sales"
        )],
        data_source="model-a",
        generated_at=NOW,
        source_mode="real",
        contract_version="2.0",
        semantic_model_key="model-a",
        schema_fingerprint="a" * 64,
        query_result_ids=["result-1"],
        verified_fact_set_ids=["facts-1"],
    ))
    assert "生成时间：" in html
    assert "最后刷新：" not in html


def test_query_time_cannot_be_used_as_refresh_authority():
    snapshot = _snapshot(data_updated_at=None).model_copy(
        update={"queried_at": UPDATED}
    )
    context = _reading_context(snapshot=snapshot)
    assert context.data_freshness.data_updated_at is None
    assert context.data_freshness.state is ReportFreshnessState.UNKNOWN


def test_sales_metric_definitions_are_registry_owned_and_unknown_basis_stays_unknown():
    assert tuple(SALES_METRIC_DEFINITIONS) == (
        "total_sales",
        "total_quantity",
        "total_orders",
        "average_order_value",
    )
    definition = SALES_METRIC_DEFINITIONS["total_sales"]
    assert definition.canonical_measure == "Total Sales"
    assert definition.tax_basis.status is MetricDefinitionStatus.UNKNOWN
    assert definition.tax_basis.value is None
    assert definition.comparison_basis.status is MetricDefinitionStatus.UNKNOWN
    assert definition.comparison_basis.value is None
    assert definition.definition_source == "registry"

    with pytest.raises(ValidationError):
        MetricDefinition(
            canonical_measure="Total Sales",
            display_name="总销售额",
            unit="currency",
            format="currency",
            aggregation="semantic_measure",
            semantic_source="Sales[Total Sales]",
            tax_basis=MetricDefinitionFacet(
                status=MetricDefinitionStatus.UNKNOWN,
                value="含税",
            ),
            comparison_basis=MetricDefinitionFacet.unknown(),
            definition_source="llm",
        )


def test_no_rule_target_or_forecast_cannot_invent_anomaly_statement():
    assessment = ExceptionAssessment.cannot_determine()
    assert assessment.state is ExceptionAssessmentState.CANNOT_DETERMINE
    assert assessment.rule_id is None
    assert assessment.evidence_fact_ids == ()
    assert assessment.message == "当前模型未提供可验证的目标、预测或异常判断基准"


def test_report_data_snapshot_has_no_generated_at_field_and_remote_is_only_reserved():
    snapshot = _snapshot()
    assert not hasattr(snapshot, "generated_at")
    with pytest.raises(ValidationError):
        ReportDataSnapshot.model_validate(
            {**snapshot.model_dump(), "generated_at": NOW}
        )
