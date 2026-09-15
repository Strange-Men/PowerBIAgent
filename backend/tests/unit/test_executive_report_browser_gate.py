"""Mutation sanity for the M5.10.2 product-level browser gate."""

from __future__ import annotations

from copy import deepcopy

from scripts.manual_smoke.executive_report_browser_acceptance import _case_failures


def _passing_geometry() -> dict[str, object]:
    return {
        "identity": "sales_executive_report",
        "rootOverflow": False,
        "overflowNodes": [],
        "sectionOverlaps": [],
        "contextBeforeNumbers": True,
        "staticRuntime": True,
        "exceptionVisible": True,
        "unknownFreshnessVisible": True,
        "noFilterVisible": True,
        "document": {"clientWidth": 1440},
        "trend": {"points": 6, "withinCard": True},
        "product": {
            "rawTokens": [],
            "hierarchyOrdered": True,
            "businessRoles": [
                "time_trend",
                "category_contribution",
                "region_comparison",
                "top_products",
                "top_customers",
            ],
            "context": {"height": 150},
            "trendSection": {"width": 1200, "height": 500},
            "kpisInFirstViewport": True,
            "layoutContract": "executive-12-column",
            "sectionOrder": [
                "executive_header", "reading_context", "kpi_summary",
                "hero_sales_trend", "business_structure", "customer_analysis",
                "audit_footer",
            ],
            "structureRoles": [
                "region_comparison", "category_contribution", "top_products",
            ],
            "customerSeparated": True,
            "kpiIconCount": 4,
            "kpiTones": ["blue", "green", "purple", "orange"],
            "chartTypes": {
                "time_trend": True,
                "region_comparison": True,
                "category_contribution": True,
                "top_products": True,
                "top_customers": True,
            },
            "customerRanks": ["1", "2"],
            "prohibitedCurrencyTokens": [],
            "donutLegendCount": 3,
            "donutOverflowNote": False,
            "templateGeometry": {
                "kpiCount": 4,
                "kpisSameRow": True,
                "structureCardCount": 3,
                "structureSameRow": True,
                "structureGridTracks": 12,
                "structureWidthSpread": 0,
                "heroWidthRatio": 1.0,
            },
        },
    }


def test_mutation_a_raw_technical_token_turns_gate_red():
    geometry = _passing_geometry()
    geometry["product"]["rawTokens"] = ["local_mcp"]
    assert "technical_tokens_in_main_visual" in _case_failures(
        "full", 1440, geometry
    )


def test_mutation_b_oversized_context_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["context"]["height"] = 420
    assert "desktop_reading_context_not_compact" in _case_failures(
        "full", 1440, geometry
    )


def test_mutation_c_missing_full_available_section_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["businessRoles"].remove("region_comparison")
    assert "full_available_section_missing" in _case_failures(
        "full", 1440, geometry
    )


def test_mutation_d_wrong_layout_contract_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["layoutContract"] = "adaptive-card-grid"
    assert "fixed_layout_contract_missing" in _case_failures("full", 1440, geometry)


def test_mutation_d2_simple_like_vertical_kpis_turn_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["templateGeometry"]["kpisSameRow"] = False
    assert "desktop_kpi_four_column_geometry_invalid" in _case_failures(
        "full", 1440, geometry
    )


def test_mutation_d3_business_structure_two_columns_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["templateGeometry"]["structureSameRow"] = False
    geometry["product"]["templateGeometry"]["structureGridTracks"] = 2
    assert "desktop_structure_three_column_geometry_invalid" in _case_failures(
        "full", 1440, geometry
    )


def test_mutation_e_kpi_icon_or_tone_loss_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["kpiIconCount"] = 3
    assert "fixed_kpi_slots_invalid" in _case_failures("full", 1440, geometry)


def test_mutation_f_adaptive_visual_substitution_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["chartTypes"]["category_contribution"] = False
    assert "fixed_visual_mapping_invalid" in _case_failures("full", 1440, geometry)


def test_mutation_g_product_leaves_three_slot_structure_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["structureRoles"].remove("top_products")
    assert "fixed_structure_slots_invalid" in _case_failures("full", 1440, geometry)


def test_mutation_h_customer_merges_into_ranking_panel_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["customerSeparated"] = False
    assert "customer_section_not_separated" in _case_failures("full", 1440, geometry)


def test_mutation_i_currency_guess_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["prohibitedCurrencyTokens"] = ["销售额（元）"]
    assert "generic_currency_guessed" in _case_failures("full", 1440, geometry)


def test_mutation_j_decimal_rank_turns_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["product"]["customerRanks"] = ["1.00", "2.00"]
    assert "customer_rank_not_integer" in _case_failures("full", 1440, geometry)


def test_mutation_k_hidden_desktop_month_labels_turn_gate_red():
    geometry = deepcopy(_passing_geometry())
    geometry["trend"] = {
        "points": 18,
        "withinCard": True,
        "desktopTickLabels": 15,
    }
    assert "desktop_trend_tick_policy_invalid" in _case_failures(
        "points_18", 1440, geometry
    )


def test_unmutated_product_geometry_is_green():
    assert _case_failures("full", 1440, _passing_geometry()) == []
