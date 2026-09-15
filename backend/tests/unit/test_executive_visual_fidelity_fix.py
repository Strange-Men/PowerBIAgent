"""Permanent regressions for the M5.10.2 executive visual-fidelity fix."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.app.report.assembly import (
    GroupedValue,
    SalesReportData,
    SalesReportSpecBuilder,
    SectionProjection,
)
from backend.app.report.executive import ExecutiveSalesReportRenderer
from backend.app.report.executive_contract import EXECUTIVE_TEMPLATE_CONTRACT
from backend.app.report.fixed import SalesReportRenderer
from backend.app.report.presentation import (
    DEFAULT_REPORT_DISPLAY_TIMEZONE,
    ProfessionalReportPresenter,
)
from scripts.manual_smoke.executive_report_visual_smoke import build_fixture


def test_repository_contract_owns_fixed_theme_layout_and_responsive_variants():
    contract = EXECUTIVE_TEMPLATE_CONTRACT

    assert contract.template_key == "sales_executive_report"
    assert contract.contract_key == "executive-12-column"
    assert contract.desktop_grid_columns == 12
    assert contract.section_order == (
        "kpi_summary",
        "hero_sales_trend",
        "business_structure",
        "customer_analysis",
        "detail",
    )
    assert contract.responsive_variants == ("desktop", "tablet", "mobile")
    assert contract.detail_variants == ("detail_available", "detail_unavailable")
    assert dict(contract.theme_tokens)["navy-950"] == "#071a33"
    with pytest.raises(FrozenInstanceError):
        contract.desktop_grid_columns = 8  # type: ignore[misc]


@pytest.mark.asyncio
async def test_executive_builder_uses_fixed_donut_while_simple_remains_adaptive():
    fixture = build_fixture("full")
    snapshot = fixture.data_snapshot
    assert snapshot is not None
    data = SalesReportData(
        template_key="sales_executive_report",
        contract_version="1.0-fixed",
        semantic_model_key=fixture.semantic_model_key,
        schema_fingerprint=fixture.schema_fingerprint,
        kpis=(),
        sections=(
            SectionProjection(
                requirement_key="sales_by_category",
                shape="grouped",
                measure="Total Sales",
                dimension="Category",
                kind="grouped",
                values=[
                    GroupedValue(label=f"Category {index}", value=Decimal(index))
                    for index in range(1, 11)
                ],
            ),
        ),
        query_result_ids=snapshot.query_result_ids,
        verified_fact_set_ids=snapshot.verified_fact_set_ids,
        source_mode="mock",
        generated_at=fixture.generated_at,
    )

    executive = SalesReportSpecBuilder().build(
        data,
        reading_context=fixture.reading_context,
        data_snapshot=snapshot,
    )
    simple = SalesReportSpecBuilder().build(
        data.model_copy(update={"template_key": "sales_report"})
    )

    assert executive.charts[0].visual_type == "donut"
    assert executive.charts[0].layout_hint == "third"
    assert simple.charts[0].visual_type == "hbar"
    executive_html = await ExecutiveSalesReportRenderer().render(executive)
    simple_html = await SalesReportRenderer().render(simple)
    assert 'data-layout-contract="executive-12-column"' in executive_html
    assert 'data-layout-contract="executive-12-column"' not in simple_html
    assert "executive-header" in executive_html
    assert "executive-header" not in simple_html
    assert "structure-grid" in executive_html
    assert "structure-grid" not in simple_html


@pytest.mark.asyncio
async def test_desktop_trend_renders_every_month_label_through_18_points():
    report = build_fixture("points_12")
    trend = report.charts[0].model_copy(
        update={
            "series": [
                {
                    "label": f"2025-{index + 1:02d}",
                    "value": 100 + index,
                    "position": None,
                }
                for index in range(18)
            ]
        }
    )
    html = await ExecutiveSalesReportRenderer().render(
        report.model_copy(update={"charts": [trend]})
    )
    desktop_ticks = html.split(
        'class="trend-ticks trend-ticks--desktop"', maxsplit=1
    )[1].split("</g>", maxsplit=1)[0]

    assert desktop_ticks.count("<text ") == 18


def test_aware_presentation_time_is_beijing_but_canonical_utc_is_unchanged():
    report = build_fixture("full")
    projection = ProfessionalReportPresenter().project(report)

    assert projection.generated_at_display == "2026-09-11 16:30 北京时间"
    assert projection.queried_at_display == "2026-09-11 16:30 北京时间"
    assert projection.canonical_generated_at == datetime(
        2026, 9, 11, 8, 30, tzinfo=timezone.utc
    ).isoformat()
    assert DEFAULT_REPORT_DISPLAY_TIMEZONE.key == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_generic_currency_never_guesses_cny_and_rank_is_integer_text():
    html = await ExecutiveSalesReportRenderer().render(build_fixture("full"))
    customer_section = html.split('data-section="customer_analysis"', maxsplit=1)[
        1
    ].split("</section>", maxsplit=1)[0]

    assert "销售额（元）" not in html
    assert "人民币" not in html
    assert "¥" not in html
    assert ">1<" in customer_section
    assert ">1.00<" not in customer_section


@pytest.mark.asyncio
async def test_fixed_structure_places_region_category_and_products_in_three_slots():
    html = await ExecutiveSalesReportRenderer().render(build_fixture("full"))
    structure = html.split('data-section="business_structure"', maxsplit=1)[1].split(
        "</section>", maxsplit=1
    )[0]

    assert 'data-layout-contract="executive-12-column"' in html
    assert 'data-business-role="region_comparison"' in structure
    assert 'data-business-role="category_contribution"' in structure
    assert 'data-business-role="top_products"' in structure
    assert 'data-section="customer_analysis"' in html
    assert "customer-analysis--ranking-only" in html
    assert 'data-detail-state="detail_unavailable"' in html
    assert 'data-section="ranking"' not in html


@pytest.mark.asyncio
async def test_fixed_kpi_cards_have_registered_icon_and_tone_slots():
    html = await ExecutiveSalesReportRenderer().render(build_fixture("full"))

    for field, tone in (
        ("Total Sales", "blue"),
        ("Total Quantity", "green"),
        ("Total Orders", "purple"),
        ("Average Order Value", "orange"),
    ):
        card = html.split(f'data-kpi="{field}"', maxsplit=1)[1].split(
            "</article>", maxsplit=1
        )[0]
        assert f'data-kpi-tone="{tone}"' in card
        assert 'class="kpi-icon"' in card
        assert "<svg" in card


@pytest.mark.asyncio
async def test_fixed_category_slot_rejects_adaptive_hbar_mutation():
    report = build_fixture("category_gt_8")
    charts = [
        item.model_copy(update={"visual_type": "hbar"})
        if item.business_role == "category_contribution"
        else item
        for item in report.charts
    ]

    with pytest.raises(
        ValueError, match="executive_report_chart_visual_role_invalid"
    ):
        await ExecutiveSalesReportRenderer().render(
            report.model_copy(update={"charts": charts})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "mutated_visual"),
    (
        ("time_trend", "column"),
        ("region_comparison", "hbar"),
        ("category_contribution", "column"),
        ("top_products", "column"),
    ),
)
async def test_each_executive_chart_slot_rejects_visual_substitution(
    role: str,
    mutated_visual: str,
):
    report = build_fixture("full")
    charts = [
        item.model_copy(update={"visual_type": mutated_visual})
        if item.business_role == role
        else item
        for item in report.charts
    ]

    with pytest.raises(ValueError, match="executive_report_chart_visual_role_invalid"):
        await ExecutiveSalesReportRenderer().render(
            report.model_copy(update={"charts": charts})
        )


@pytest.mark.asyncio
async def test_fixed_visual_contract_does_not_fabricate_reference_only_facts():
    html = await ExecutiveSalesReportRenderer().render(build_fixture("full"))

    assert {
        slot.business_role: slot.visual_type
        for slot in EXECUTIVE_TEMPLATE_CONTRACT.visual_slots
    } == {
        "time_trend": "line",
        "region_comparison": "column",
        "category_contribution": "donut",
        "top_products": "hbar",
        "top_customers": "table",
    }
    for unsupported in (
        "YoY", "MoM", "Forecast", "Target", "Budget",
        "Customer Concentration", "AI Insight", "同比", "环比",
    ):
        assert unsupported not in html


def test_naive_presentation_time_remains_explicitly_unzoned():
    value = datetime(2026, 9, 11, 8, 30)

    assert ProfessionalReportPresenter._format_datetime(value) == (
        "2026-09-11 08:30（时区未声明）"
    )
