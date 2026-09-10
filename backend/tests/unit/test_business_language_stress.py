"""M5.9.4 Business Language Stress generator and failure reproducers."""

from __future__ import annotations

import json

import pytest

from backend.app.intent.question_router import QuestionRouter
from backend.app.intent.temporal_expression import parse_explicit_month_range
from backend.app.query_plan.grounding import SemanticGroundingService
from backend.app.query_plan.turn_relation import TurnRelationEvidence, TurnRelationKind
from backend.app.schemas.data_contracts import QueryShape
from backend.tests.stress.business_language_stress import (
    DEFAULT_SEED,
    BusinessLanguageStressHarness,
    coverage_matrix,
    generate_cases,
    greedy_pairwise_rows,
)


def test_pairwise_generator_is_seeded_complete_and_deterministic() -> None:
    factors = {
        "shape": ("scalar", "grouped", "ranking"),
        "relation": ("fresh", "follow_up", "replace"),
        "language": ("formal", "spoken", "mixed"),
        "member": ("known", "unknown"),
    }
    first = greedy_pairwise_rows(factors, seed=DEFAULT_SEED)
    second = greedy_pairwise_rows(factors, seed=DEFAULT_SEED)

    assert first == second
    for left_index, left in enumerate(factors):
        for right in tuple(factors)[left_index + 1 :]:
            observed = {(row[left], row[right]) for row in first}
            expected = {
                (left_value, right_value)
                for left_value in factors[left]
                for right_value in factors[right]
            }
            assert observed == expected


def test_generator_covers_51200_safe_reproducible_cases() -> None:
    first = list(generate_cases())
    second = list(generate_cases())
    matrix = coverage_matrix(first)

    assert len(first) == 51_200
    assert [item.case_id for item in first] == [item.case_id for item in second]
    assert [item.question for item in first] == [item.question for item in second]
    assert set(matrix["by_shape"]) == {shape.value for shape in QueryShape}
    assert set(matrix["by_domain"]) == {
        "sales_star_duplicate",
        "education_snowflake",
        "inventory_flat_multidate",
        "logistics_technical_label_peer",
    }
    assert all(count == 12_800 for count in matrix["by_domain"].values())
    serialized = json.dumps(first[0].safe_descriptor(), ensure_ascii=False)
    assert "connection" not in serialized.casefold()
    assert ".pbix" not in serialized.casefold()


@pytest.mark.parametrize(
    ("question", "shape", "top_n"),
    [
        ("华南和华北一起的销售额是多少", QueryShape.FILTERED_AGGREGATION, None),
        ("请问上个月各产品净营收", QueryShape.GROUPED, None),
        ("华南的产品净营收分别是多少，2025年5月", QueryShape.GROUPED, None),
        ("请问list all 产品", QueryShape.ENTITY_LIST, None),
        ("重新分析：2025年5月净营收", QueryShape.SCALAR, None),
        ("其中华南净营收是多少", None, None),
        ("前几个产品销售额", QueryShape.RANKING, None),
        ("第一个产品销售额", QueryShape.RANKING, 1),
    ],
)
def test_minimal_adversarial_shape_reproducers(
    question: str, shape: QueryShape | None, top_n: int | None
) -> None:
    decision = QuestionRouter().route(question)

    assert decision.query_shape == shape
    if shape == QueryShape.RANKING:
        assert SemanticGroundingService._extract_top_n(question) == top_n


def test_among_prefix_is_explicit_follow_up_evidence() -> None:
    evidence = TurnRelationEvidence.classify("其中华南净营收是多少")

    assert evidence.kind == TurnRelationKind.FOLLOW_UP
    assert evidence.explicit


@pytest.mark.parametrize(
    "question",
    [
        "今年1月至6月每个月的销售额趋势",
        "今年1月到6月销售额月趋势",
        "今年1月-6月按月看销售额",
        "今年1月~6月销售额变化",
    ],
)
def test_relative_year_bounded_range_minimal_reproducer(question: str) -> None:
    decision = QuestionRouter().route(question)
    parsed = parse_explicit_month_range(question, reference_year=2026)

    assert decision.query_shape == QueryShape.BOUNDED_TREND
    assert parsed is not None
    assert (parsed.start_year, parsed.start_month) == (2026, 1)
    assert (parsed.end_year, parsed.end_month) == (2026, 6)


def test_yearless_bounded_range_is_detected_but_not_invented() -> None:
    question = "1月到6月每个月的销售额趋势"

    assert QuestionRouter().route(question).query_shape == QueryShape.BOUNDED_TREND
    assert parse_explicit_month_range(question, reference_year=2026) is None


def test_stress_report_has_zero_generated_failures() -> None:
    summary = BusinessLanguageStressHarness().run()

    assert summary.total == 51_200
    assert summary.as_dict()["fail"] == 0, json.dumps(
        summary.as_dict(), ensure_ascii=False, indent=2
    )
