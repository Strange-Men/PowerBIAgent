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


def test_unmutated_product_geometry_is_green():
    assert _case_failures("full", 1440, _passing_geometry()) == []
