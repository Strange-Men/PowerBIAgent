from datetime import datetime, timezone

import pytest

from backend.app.intent.question_router import QuestionRoute, QuestionRouter
from backend.app.report.intent import (
    ReportCoverageMode,
    ReportIntentDraft,
    full_requested_ids,
    resolve_report_intent,
)
from backend.app.report.presentation import ProfessionalReportPresenter
from backend.app.report.capability import SectionKey
from backend.app.report.plan import ReportPlanner
from backend.app.schemas.data_contracts import ReportSpec
from backend.app.schemas.report_context import ReportDataSourceKind
from backend.tests.unit.test_executive_report_renderer import _report
from backend.tests.unit.test_report_adaptive import _rich_schema, _rich_without


@pytest.mark.parametrize(
    "question",
    (
        "生成一份完整的销售经营分析报表",
        "生成完整销售报表",
        "给我一份销售经营分析报告",
        "生成一份完整经营报告",
        "生成销售分析报告",
        "生成报表",
    ),
)
def test_explicit_report_generation_language_routes_before_metric_clarification(
    question: str,
):
    assert QuestionRouter().route(question).route is QuestionRoute.REPORT_REQUEST


@pytest.mark.parametrize(
    "question",
    (
        "报表里的销售额是多少？",
        "报告中的订单数是多少？",
        "这份报表为什么没有客户？",
        "销售额是多少？",
    ),
)
def test_report_content_questions_do_not_become_generation_requests(question: str):
    assert QuestionRouter().route(question).route is QuestionRoute.BUSINESS_DATA_QUERY


def test_full_available_is_explicit_and_weak_llm_cannot_shrink_it():
    draft = ReportIntentDraft(report_section_ids=["sales_kpi", "time_trend"])

    signal = resolve_report_intent(
        "生成一份完整的销售经营分析报表",
        llm_draft=draft,
    )

    assert signal.coverage_mode is ReportCoverageMode.FULL_AVAILABLE
    assert signal.requested_ids == full_requested_ids()
    assert signal.llm_draft_ids == ("sales_kpi", "time_trend")


def test_ordinary_report_request_uses_requested_coverage():
    signal = resolve_report_intent("生成销售趋势报表")

    assert signal.coverage_mode is ReportCoverageMode.REQUESTED
    assert signal.requested_ids == ("sales_kpi", "time_trend")


def test_full_available_budget_cannot_silently_drop_available_sections():
    from backend.app.report.plan import ReportPlanError, ReportPlanner

    signal = resolve_report_intent("生成一份完整的销售经营分析报表")
    with pytest.raises(
        ReportPlanError,
        match="report_full_coverage_budget_insufficient",
    ):
        ReportPlanner().plan(
            "sales_executive_report",
            _rich_schema(),
            signal.requested_ids,
            signal,
            max_queries=6,
        )


@pytest.mark.parametrize(
    ("missing_object", "missing_section"),
    (
        ("Region", SectionKey.REGION_COMPARISON),
        ("Category", SectionKey.CATEGORY_CONTRIBUTION),
        ("Product", SectionKey.TOP_PRODUCTS),
        ("Customer", SectionKey.TOP_CUSTOMERS),
        ("Date", SectionKey.TIME_TREND),
    ),
)
def test_full_available_respects_runtime_partial_capability_with_reason(
    missing_object: str,
    missing_section: SectionKey,
):
    signal = resolve_report_intent("生成一份完整的销售经营分析报表")

    plan = ReportPlanner().plan(
        "sales_executive_report",
        _rich_without(missing_object),
        signal.requested_ids,
        signal,
    )

    assert missing_section not in plan.resolved_sections
    assert missing_section in plan.unavailable_sections
    assert plan.section_capabilities[missing_section].reason.startswith(
        "report_requirement_unavailable:"
    )


def test_professional_projection_keeps_canonical_identity_but_humanizes_main_text():
    report = _report()
    snapshot = report.data_snapshot.model_copy(update={
        "semantic_model_display_name": "华东销售分析模型",
        "source_display_name": "Power BI Desktop",
    })
    report = report.model_copy(update={"data_snapshot": snapshot})

    projection = ProfessionalReportPresenter().project(report)

    assert projection.model_display_name == "华东销售分析模型"
    assert projection.source_display_name == "Power BI Desktop · 实时查询"
    assert projection.exception_display == "暂无可验证异常基准"
    assert projection.freshness_display == "暂不可获取"
    assert projection.generated_at_display.endswith(" 北京时间")
    assert projection.canonical_model_identity == "local_desktop:model-a"
    assert projection.canonical_source_kind is ReportDataSourceKind.LOCAL_MCP
    assert projection.canonical_source_mode == "real"
    assert "cannot_determine" not in projection.main_text
    assert "UNKNOWN" not in projection.main_text
    assert "semantic_measure" not in projection.main_text
    assert "local_desktop:model-a" not in projection.main_text


def test_professional_projection_falls_back_without_exposing_opaque_model_id():
    projection = ProfessionalReportPresenter().project(_report())

    assert projection.model_display_name == "当前 Power BI Desktop 模型"
    assert "local_desktop:model-a" not in projection.main_text


def test_professional_projection_never_guesses_timezone_for_naive_datetime():
    report: ReportSpec = _report()
    context = report.reading_context.model_copy(
        update={"generated_at": datetime(2026, 9, 14, 2, 28, 10)}
    )
    report = report.model_copy(
        update={"generated_at": context.generated_at, "reading_context": context}
    )

    projection = ProfessionalReportPresenter().project(report)

    assert projection.generated_at_display == "2026-09-14 02:28（时区未声明）"
    assert "+08" not in projection.generated_at_display
    assert "10:28" not in projection.generated_at_display


def test_naive_datetime_formatter_keeps_strftime_format_locale_ascii_safe():
    class AsciiFormatDatetime(datetime):
        def strftime(self, format_string: str) -> str:
            assert format_string.isascii()
            return super().strftime(format_string)

    value = AsciiFormatDatetime(2026, 9, 14, 2, 28, 10)

    assert ProfessionalReportPresenter._format_datetime(value) == (
        "2026-09-14 02:28（时区未声明）"
    )


def test_remote_source_is_projection_only_and_does_not_add_transport_contract():
    report = _report()
    snapshot = report.data_snapshot.model_copy(update={
        "source_kind": ReportDataSourceKind.REMOTE_MCP,
        "source_display_name": "公司 Power BI 服务",
    })
    context = report.reading_context.model_copy(update={
        "data_source": report.reading_context.data_source.model_copy(update={
            "kind": ReportDataSourceKind.REMOTE_MCP,
            "display_name": "公司 Power BI 服务",
        })
    })
    report = report.model_copy(update={
        "data_snapshot": snapshot,
        "reading_context": context,
    })

    projection = ProfessionalReportPresenter().project(report)

    assert projection.source_display_name == "公司 Power BI 服务 · 实时查询"
    assert projection.canonical_source_kind is ReportDataSourceKind.REMOTE_MCP
