"""Permanent 18-scenario visual-fixture and renderer performance gate."""

from __future__ import annotations

import pytest

from scripts.manual_smoke.executive_report_visual_smoke import (
    SCENARIO_NAMES,
    render_fixture,
)


def test_executive_visual_fixture_matrix_is_exact_and_bounded():
    assert SCENARIO_NAMES == (
        "full", "kpi_only", "trend_only", "region_category", "ranking",
        "missing_optional", "no_filter", "multiple_filters",
        "unknown_freshness", "long_product", "long_customer",
        "category_gt_8", "points_1", "points_2", "points_6",
        "points_12", "points_18", "points_24", "points_60",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
async def test_each_executive_visual_fixture_renders_static_html(scenario: str):
    html, elapsed_ms = await render_fixture(scenario)

    assert html.startswith("<!DOCTYPE html>")
    assert 'data-template-key="sales_executive_report"' in html
    assert "销售经营分析报告" in html
    assert "暂无可验证异常基准" in html
    assert len(html.encode("utf-8")) < 500_000
    assert elapsed_ms < 500
    lowered = html.casefold()
    assert all(token not in lowered for token in (
        "<script", "javascript:", "http://", "https://", "<link", "@import", "url("
    ))


@pytest.mark.asyncio
async def test_fixture_edge_states_are_visible_not_silently_defaulted():
    no_filter, _ = await render_fixture("no_filter")
    unknown, _ = await render_fixture("unknown_freshness")
    long_product, _ = await render_fixture("long_product")
    long_customer, _ = await render_fixture("long_customer")
    sixty, _ = await render_fixture("points_60")

    assert "无额外筛选" in no_filter
    assert "暂不可获取" in unknown
    assert "超长名称企业级智能协作终端旗舰套装" in long_product
    assert "超长名称跨区域企业集团重点战略客户" in long_customer
    assert sixty.count('class="trend-point"') == 60
