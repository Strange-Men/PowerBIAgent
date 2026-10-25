"""Natural-language stress harness invariants (test-side oracle only)."""

from __future__ import annotations

from backend.tests.stress.natural_language_semantic_stress import (
    DimensionProfile,
    MeasureProfile,
    MemberProfile,
    StressModelProfile,
    assert_natural_questions,
    evaluate_case,
    generate_cases,
    generate_matrix,
)


def profiles() -> tuple[StressModelProfile, ...]:
    return (
        StressModelProfile(
            key="retail",
            label="Retail",
            measures=(
                MeasureProfile("Total Sales", "sales"),
                MeasureProfile("Total Quantity", "quantity"),
            ),
            dimensions=(
                DimensionProfile("City", "Geography", "city", "cities"),
                DimensionProfile("Product", "Product", "product", "products"),
            ),
            members=(
                MemberProfile("City", "Shanghai", "Shanghai"),
                MemberProfile("Product", "Mountain Bike", "Mountain Bike"),
            ),
            date_field="OrderDate",
            ambiguous_phrase="performance",
            localized_measure="销售额",
            localized_dimension="城市",
        ),
        StressModelProfile(
            key="education",
            label="Education",
            measures=(
                MeasureProfile("Pass Rate", "pass rate"),
                MeasureProfile("Enrollment Count", "enrollment"),
            ),
            dimensions=(
                DimensionProfile("Program", "Programs", "program", "programs"),
                DimensionProfile("Campus", "Campuses", "campus", "campuses"),
            ),
            members=(MemberProfile("Program", "Data Science", "Data Science"),),
            date_field="AcademicMonth",
            ambiguous_phrase="attendance",
        ),
        StressModelProfile(
            key="operations",
            label="Operations",
            measures=(
                MeasureProfile("On Hand Units", "on-hand units"),
                MeasureProfile("Reserved Units", "reserved units"),
            ),
            dimensions=(
                DimensionProfile("Warehouse", "Warehouses", "warehouse", "warehouses"),
                DimensionProfile("Bin", "Bins", "bin", "bins"),
            ),
            members=(MemberProfile("Warehouse", "North Hub", "North Hub"),),
            date_field="CaptureMonth",
            ambiguous_phrase="inventory",
        ),
    )


def test_three_model_matrix_is_bounded_natural_and_covers_required_family():
    matrix = generate_matrix(profiles())

    assert 48 <= len(matrix) <= 72
    assert {item.model_key for item in matrix} == {"retail", "education", "operations"}
    assert_natural_questions(matrix)
    kinds = {item.kind for item in matrix}
    assert {
        "scalar",
        "grouped",
        "ranking_desc",
        "ranking_asc",
        "member_filter",
        "multi_measure",
        "time_range",
        "bounded_trend",
        "trend",
        "follow_up_measure",
        "follow_up_filter",
        "fresh_reset",
        "ambiguity",
        "member_no_match",
        "unknown_term",
        "cross_language",
    } <= kinds
    for case in matrix:
        assert "table[" not in case.question.casefold()
        assert case.oracle()["shape"] in {
            "scalar", "grouped", "ranking", "filtered_aggregation",
            "bounded_trend", "trend", None,
        }


def _audit(
    *,
    state="completed",
    shape="scalar",
    measures=("Total Sales",),
    dimensions=(),
    filters=(),
    time_range=None,
    sort=None,
    top_n=None,
    relation="fresh_question",
):
    plan = {
        "query_shape": shape,
        "measures": list(measures),
        "dimensions": list(dimensions),
        "filters": [
            {"field": field, "operator": "eq", "value": value}
            for field, value in filters
        ],
        "time_range": time_range,
        "sort": sort,
        "top_n": top_n,
    }
    return {
        "terminal_state": state,
        "memory_commit": state == "completed",
        "answer": "verified answer" if state == "completed" else None,
        "execution_audit": {
            "semantic_frame": {"query_shape": shape},
            "canonical_query_plan": plan,
            "turn_relation_evidence": {"kind": relation},
        },
    }


def test_evaluate_case_passes_and_classifies_first_wrong_layer():
    cases = generate_cases(profiles()[0])
    scalar = next(item for item in cases if item.kind == "scalar")
    assert evaluate_case(scalar, _audit()).outcome == "PASS"

    wrong_measure = evaluate_case(
        scalar, _audit(measures=("Total Quantity",))
    )
    assert wrong_measure.outcome == "FAIL"
    assert wrong_measure.layer == "RESOLUTION"

    grouped = next(item for item in cases if item.kind == "grouped")
    wrong_dimension = evaluate_case(
        grouped, _audit(shape="grouped", dimensions=("Product",))
    )
    assert wrong_dimension.layer == "RESOLUTION"

    member_case = next(item for item in cases if item.kind == "member_filter")
    wrong_member = evaluate_case(
        member_case,
        _audit(
            shape="filtered_aggregation",
            filters=(("City", "Beijing"),),
        ),
    )
    assert wrong_member.layer == "MEMBER"

    time_case = next(item for item in cases if item.kind == "time_range")
    wrong_time = evaluate_case(
        time_case,
        _audit(time_range={"start_date": "2025-07-01", "end_date": "2025-12-31"}),
    )
    assert wrong_time.layer == "TEMPORAL"

    ambiguous = next(item for item in cases if item.kind == "ambiguity")
    assert evaluate_case(
        ambiguous,
        _audit(state="clarification_required"),
    ).outcome == "CLARIFICATION"
    assert evaluate_case(ambiguous, _audit()).outcome == "FAIL"

    follow = next(item for item in cases if item.kind == "follow_up_measure")
    assert evaluate_case(
        follow,
        _audit(measures=("Total Quantity",), relation="fresh_question"),
    ).layer == "STATE"
