"""Independent Known-answer Oracle contract tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.harness.oracles.known_answer import (
    BaselineSource,
    KnownAnswerBaseline,
    KnownAnswerOracle,
    OracleMode,
)
from backend.app.schemas.data_contracts import QueryResult


ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "harness" / "baselines" / "example_known_answers.yaml"


def _oracle(real_path: Path) -> KnownAnswerOracle:
    return KnownAnswerOracle(EXAMPLE, real_path)


def _result(columns: list[str], rows: list[list[object]]) -> QueryResult:
    return QueryResult(
        semantic_model_key="fictional_model",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        source_mode="mock",
    )


def test_scalar_exact_match(tmp_path: Path):
    evaluation = _oracle(tmp_path / "missing.yaml").evaluate(
        "total_quantity", _result(["[Total Quantity]"], [[42]])
    )
    assert evaluation.passed


def test_scalar_numeric_tolerance_is_small_and_explicit(tmp_path: Path):
    evaluation = _oracle(tmp_path / "missing.yaml").evaluate(
        "total_sales", _result(["[Total Sales]"], [[1000.2500001]])
    )
    assert evaluation.passed


def test_scalar_mismatch_fails(tmp_path: Path):
    evaluation = _oracle(tmp_path / "missing.yaml").evaluate(
        "total_sales", _result(["[Total Sales]"], [[1000.35]])
    )
    assert not evaluation.passed
    assert evaluation.code == "value_mismatch"


def test_grouped_rows_are_canonicalized_by_business_key(tmp_path: Path):
    actual = _result(
        ["Category", "[Total Sales]"],
        [["Furniture", 330.05], ["Office", 260.10], ["Electronics", 410.10]],
    )
    assert _oracle(tmp_path / "missing.yaml").evaluate(
        "sales_by_category", actual
    ).passed


def test_grouped_missing_row_fails(tmp_path: Path):
    actual = _result(
        ["Category", "[Total Sales]"],
        [["Furniture", 330.05], ["Electronics", 410.10]],
    )
    evaluation = _oracle(tmp_path / "missing.yaml").evaluate(
        "sales_by_category", actual
    )
    assert not evaluation.passed
    assert "business keys mismatch" in evaluation.mismatches[0]


def test_grouped_wrong_metric_fails(tmp_path: Path):
    actual = _result(
        ["Category", "[Total Sales]"],
        [["Office", 260.10], ["Electronics", 999.0], ["Furniture", 330.05]],
    )
    assert not _oracle(tmp_path / "missing.yaml").evaluate(
        "sales_by_category", actual
    ).passed


def test_ordered_result_rejects_rows_beyond_top_n_even_when_metric_ties(tmp_path: Path):
    actual = _result(
        ["Product", "[Total Sales]"],
        [
            ["Alpha", 300.0],
            ["Beta", 250.0],
            ["Delta", 200.0],
            ["Gamma", 200.0],
        ],
    )
    evaluation = _oracle(tmp_path / "missing.yaml").evaluate(
        "top3_products_sales", actual
    )
    assert not evaluation.passed
    assert len(actual.rows) == 4


def test_ordered_result_wrong_order_fails(tmp_path: Path):
    actual = _result(
        ["Product", "[Total Sales]"],
        [
            ["Beta", 250.0],
            ["Alpha", 300.0],
            ["Gamma", 200.0],
            ["Delta", 200.0],
        ],
    )
    assert not _oracle(tmp_path / "missing.yaml").evaluate(
        "top3_products_sales", actual
    ).passed


def test_column_mismatch_fails(tmp_path: Path):
    evaluation = _oracle(tmp_path / "missing.yaml").evaluate(
        "total_sales", _result(["Wrong Metric"], [[1000.25]])
    )
    assert not evaluation.passed
    assert evaluation.code == "column_mismatch"


def test_local_real_baseline_missing_is_explicit_and_never_falls_back(tmp_path: Path):
    oracle = _oracle(tmp_path / "missing-real-baseline.yaml")
    actual = _result(["[Total Sales]"], [[1000.25]])
    evaluation = oracle.evaluate(
        "total_sales", actual, source=BaselineSource.REAL_LOCAL
    )
    assert not evaluation.passed
    assert evaluation.code == "real_baseline_not_configured"


def test_actual_cannot_be_used_to_synthesize_missing_expected(tmp_path: Path):
    oracle = _oracle(tmp_path / "missing.yaml")
    actual = _result(["Anything"], [[123]])
    evaluation = oracle.evaluate("not_in_baseline", actual)
    assert not evaluation.passed
    assert evaluation.code == "baseline_not_found"


def test_none_comparison_is_explicit(tmp_path: Path):
    baseline = KnownAnswerBaseline(
        oracle_key="nullable",
        mode=OracleMode.SCALAR,
        expected_columns=["Metric"],
        metric_columns=["Metric"],
        expected_value=None,
    )
    oracle = _oracle(tmp_path / "missing.yaml")
    assert oracle.compare(baseline, _result(["Metric"], [[None]])).passed
    assert not oracle.compare(baseline, _result(["Metric"], [[0]])).passed


def test_huge_numeric_tolerance_is_rejected():
    with pytest.raises(ValidationError):
        KnownAnswerBaseline(
            oracle_key="too_loose",
            mode=OracleMode.SCALAR,
            expected_columns=["Metric"],
            metric_columns=["Metric"],
            expected_value=100,
            tolerance={"abs_tolerance": 100, "rel_tolerance": 1},
        )


def test_real_baseline_must_cover_all_required_oracle_keys(tmp_path: Path):
    real_path = tmp_path / "real.yaml"
    real_path.write_text(
        """baselines:
  - oracle_key: only_one
    mode: scalar
    expected_columns: [Metric]
    metric_columns: [Metric]
    expected_value: 1
""",
        encoding="utf-8",
    )
    configured, code, count = _oracle(real_path).validate_keys(
        BaselineSource.REAL_LOCAL, {"only_one", "missing"}
    )
    assert not configured
    assert code == "real_baseline_incomplete"
    assert count == 1
