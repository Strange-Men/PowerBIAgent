"""Independent Known-answer Oracle for Harness and acceptance tests.

Expected values are loaded only from an explicit baseline file. The comparator
never derives expected values from DAX, an LLM answer, or the actual
``QueryResult`` under test.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from numbers import Number
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.data_contracts import QueryResult


class OracleMode(str, Enum):
    SCALAR = "scalar"
    GROUPED = "grouped"
    ORDERED = "ordered"


class BaselineSource(str, Enum):
    EXAMPLE = "example"
    REAL_LOCAL = "real_local"


class NumericTolerance(BaseModel):
    """Small, explicit tolerance used only for numeric values."""

    abs_tolerance: Decimal = Field(default=Decimal("1e-9"), ge=0, le=Decimal("0.01"))
    rel_tolerance: Decimal = Field(
        default=Decimal("1e-9"), ge=0, le=Decimal("0.000001")
    )

    model_config = ConfigDict(extra="forbid")


class KnownAnswerBaseline(BaseModel):
    """Independent expected result for one semantic Known-answer case."""

    oracle_key: str = Field(min_length=1)
    mode: OracleMode
    expected_columns: list[str] = Field(min_length=1)
    metric_columns: list[str] = Field(min_length=1)
    key_columns: list[str] = Field(default_factory=list)
    expected_value: Any = None
    expected_rows: list[dict[str, Any]] = Field(default_factory=list)
    tolerance: NumericTolerance = Field(default_factory=NumericTolerance)
    sort: str | None = Field(default=None, pattern="^(asc|desc)$")
    top_n: int | None = Field(default=None, ge=1)
    allow_top_n_ties: bool = True

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_shape(self) -> "KnownAnswerBaseline":
        if len(set(self.expected_columns)) != len(self.expected_columns):
            raise ValueError("expected_columns must be unique")
        column_set = set(self.expected_columns)
        if not set(self.metric_columns).issubset(column_set):
            raise ValueError("metric_columns must be included in expected_columns")
        if not set(self.key_columns).issubset(column_set):
            raise ValueError("key_columns must be included in expected_columns")

        if self.mode == OracleMode.SCALAR:
            if self.key_columns or self.expected_rows:
                raise ValueError("scalar baseline cannot define keys or expected_rows")
            if len(self.metric_columns) != 1:
                raise ValueError("scalar baseline requires exactly one metric column")
            if "expected_value" not in self.model_fields_set:
                raise ValueError("scalar baseline must explicitly define expected_value")
            if self.expected_value is not None and not KnownAnswerOracle._is_numeric(
                self.expected_value
            ):
                raise ValueError("scalar expected_value must be numeric or None")
        else:
            if not self.key_columns:
                raise ValueError("grouped/ordered baseline requires key_columns")
            if not self.expected_rows:
                raise ValueError("grouped/ordered baseline requires expected_rows")
            for index, row in enumerate(self.expected_rows):
                if set(row) != column_set:
                    raise ValueError(
                        f"expected_rows[{index}] columns must exactly match expected_columns"
                    )
                for metric in self.metric_columns:
                    if row[metric] is not None and not KnownAnswerOracle._is_numeric(
                        row[metric]
                    ):
                        raise ValueError(
                            f"expected_rows[{index}].{metric} must be numeric or None"
                        )

        if self.mode != OracleMode.ORDERED and (self.sort is not None or self.top_n is not None):
            raise ValueError("sort/top_n are only valid for ordered baselines")
        if self.mode == OracleMode.ORDERED and self.sort is None:
            raise ValueError("ordered baseline requires sort")
        if self.top_n is not None and self.sort is None:
            raise ValueError("ordered top_n baseline requires sort")
        if self.mode == OracleMode.ORDERED:
            self._validate_expected_order()
        return self

    def _validate_expected_order(self) -> None:
        if self.sort is None:
            return
        if len(self.metric_columns) != 1:
            raise ValueError("ordered baseline requires exactly one metric column")
        metric = self.metric_columns[0]
        values = [KnownAnswerOracle._to_decimal(row[metric]) for row in self.expected_rows]
        if any(value is None for value in values):
            raise ValueError("ordered metric values must be finite numerics")
        numeric_values = [value for value in values if value is not None]
        expected_order = sorted(numeric_values, reverse=self.sort == "desc")
        if numeric_values != expected_order:
            raise ValueError("expected_rows do not follow the declared sort")
        if self.top_n is not None and len(numeric_values) > self.top_n:
            if not self.allow_top_n_ties:
                raise ValueError("expected_rows exceed top_n while ties are disabled")
            boundary = numeric_values[self.top_n - 1]
            if any(value != boundary for value in numeric_values[self.top_n :]):
                raise ValueError("rows beyond top_n must tie the Nth metric value")


class OracleEvaluation(BaseModel):
    oracle_key: str
    passed: bool
    code: str
    mismatches: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class KnownAnswerOracle:
    """Compare an actual ``QueryResult`` with an independent file baseline."""

    def __init__(self, example_path: Path, real_local_path: Path):
        self.example_path = Path(example_path)
        self.real_local_path = Path(real_local_path)
        self._cache: dict[BaselineSource, dict[str, KnownAnswerBaseline]] = {}

    def evaluate(
        self,
        oracle_key: str,
        actual: QueryResult | None,
        *,
        source: BaselineSource = BaselineSource.EXAMPLE,
    ) -> OracleEvaluation:
        baselines, load_error = self._load(source)
        if load_error is not None:
            return OracleEvaluation(
                oracle_key=oracle_key,
                passed=False,
                code=load_error,
                mismatches=[load_error],
            )
        baseline = baselines.get(oracle_key)
        if baseline is None:
            return OracleEvaluation(
                oracle_key=oracle_key,
                passed=False,
                code="baseline_not_found",
                mismatches=[f"baseline_not_found:{oracle_key}"],
            )
        return self.compare(baseline, actual)

    def validate_source(
        self, source: BaselineSource
    ) -> tuple[bool, str, int]:
        """Validate baseline availability/schema without exposing expected values."""
        baselines, load_error = self._load(source)
        if load_error is not None:
            return False, load_error, 0
        return True, "configured", len(baselines)

    def validate_keys(
        self,
        source: BaselineSource,
        required_keys: set[str],
    ) -> tuple[bool, str, int]:
        """Require complete baseline coverage without exposing expected values."""
        baselines, load_error = self._load(source)
        if load_error is not None:
            return False, load_error, 0
        if required_keys - set(baselines):
            return False, "real_baseline_incomplete", len(baselines)
        return True, "configured", len(baselines)

    def compare(
        self,
        baseline: KnownAnswerBaseline,
        actual: QueryResult | None,
    ) -> OracleEvaluation:
        mismatches: list[str] = []
        if actual is None:
            return self._failure(baseline.oracle_key, "actual_query_result_missing")
        if actual.error is not None:
            return self._failure(baseline.oracle_key, "actual_query_result_error")
        if actual.columns != baseline.expected_columns:
            return self._failure(
                baseline.oracle_key,
                "column_mismatch",
                f"expected columns {baseline.expected_columns}, got {actual.columns}",
            )

        rows = [dict(zip(actual.columns, row, strict=True)) for row in actual.rows]
        if baseline.mode == OracleMode.SCALAR:
            if len(rows) != 1:
                mismatches.append(f"expected 1 scalar row, got {len(rows)}")
            else:
                metric = baseline.metric_columns[0]
                self._compare_value(
                    baseline.expected_value,
                    rows[0][metric],
                    metric,
                    baseline.tolerance,
                    mismatches,
                )
        elif baseline.mode == OracleMode.GROUPED:
            mismatches.extend(self._compare_grouped(baseline, rows))
        else:
            mismatches.extend(self._compare_ordered(baseline, rows))

        return OracleEvaluation(
            oracle_key=baseline.oracle_key,
            passed=not mismatches,
            code="pass" if not mismatches else "value_mismatch",
            mismatches=mismatches,
        )

    def _load(
        self, source: BaselineSource
    ) -> tuple[dict[str, KnownAnswerBaseline], str | None]:
        if source in self._cache:
            return self._cache[source], None
        path = self.example_path if source == BaselineSource.EXAMPLE else self.real_local_path
        if not path.is_file():
            code = (
                "real_baseline_not_configured"
                if source == BaselineSource.REAL_LOCAL
                else "example_baseline_not_configured"
            )
            return {}, code
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return {}, "baseline_schema_invalid"
        definitions = raw.get("baselines")
        if not isinstance(definitions, list):
            return {}, "baseline_schema_invalid"
        try:
            parsed = [KnownAnswerBaseline.model_validate(item) for item in definitions]
        except Exception:
            return {}, "baseline_schema_invalid"
        by_key = {item.oracle_key: item for item in parsed}
        if len(by_key) != len(parsed):
            return {}, "baseline_schema_invalid"
        self._cache[source] = by_key
        return by_key, None

    def _compare_grouped(
        self, baseline: KnownAnswerBaseline, actual_rows: list[dict[str, Any]]
    ) -> list[str]:
        expected, expected_error = self._index_by_key(
            baseline.expected_rows, baseline.key_columns
        )
        actual, actual_error = self._index_by_key(actual_rows, baseline.key_columns)
        if expected_error or actual_error:
            return [error for error in (expected_error, actual_error) if error]
        if set(expected) != set(actual):
            return [
                "grouped business keys mismatch: "
                f"expected {self._stable_keys(expected)}, got {self._stable_keys(actual)}"
            ]
        mismatches: list[str] = []
        for key in sorted(expected, key=self._stable_key):
            self._compare_row(
                baseline, expected[key], actual[key], f"key={key!r}", mismatches
            )
        return mismatches

    def _compare_ordered(
        self, baseline: KnownAnswerBaseline, actual_rows: list[dict[str, Any]]
    ) -> list[str]:
        if len(actual_rows) != len(baseline.expected_rows):
            return [
                f"ordered row count mismatch: expected {len(baseline.expected_rows)}, "
                f"got {len(actual_rows)}"
            ]
        # Compare membership and values by business key, while validating the
        # presentation order independently. This permits arbitrary ordering
        # among rows tied on the sort metric.
        mismatches = self._compare_grouped(baseline, actual_rows)
        metric = baseline.metric_columns[0]
        numeric_values = [self._to_decimal(row[metric]) for row in actual_rows]
        if any(value is None for value in numeric_values):
            mismatches.append("ordered metric contains non-finite/non-numeric value")
            return mismatches
        values = [value for value in numeric_values if value is not None]
        for index, (left, right) in enumerate(zip(values, values[1:])):
            permitted = max(
                baseline.tolerance.abs_tolerance,
                baseline.tolerance.rel_tolerance * max(abs(left), abs(right)),
            )
            if baseline.sort == "desc" and left + permitted < right:
                mismatches.append(f"ordered direction mismatch at rows {index}/{index + 1}")
            if baseline.sort == "asc" and left - permitted > right:
                mismatches.append(f"ordered direction mismatch at rows {index}/{index + 1}")
        return mismatches

    def _compare_row(
        self,
        baseline: KnownAnswerBaseline,
        expected: dict[str, Any],
        actual: dict[str, Any],
        location: str,
        mismatches: list[str],
    ) -> None:
        for column in baseline.expected_columns:
            if column in baseline.key_columns:
                continue
            self._compare_value(
                expected[column],
                actual[column],
                f"{location}.{column}",
                baseline.tolerance,
                mismatches,
            )

    @staticmethod
    def _compare_value(
        expected: Any,
        actual: Any,
        location: str,
        tolerance: NumericTolerance,
        mismatches: list[str],
    ) -> None:
        if expected is None or actual is None:
            if expected is not actual:
                mismatches.append(f"{location}: expected {expected!r}, got {actual!r}")
            return
        if KnownAnswerOracle._is_numeric(expected) and KnownAnswerOracle._is_numeric(actual):
            expected_decimal = KnownAnswerOracle._to_decimal(expected)
            actual_decimal = KnownAnswerOracle._to_decimal(actual)
            if expected_decimal is None or actual_decimal is None:
                mismatches.append(f"{location}: non-finite numeric value")
                return
            difference = abs(expected_decimal - actual_decimal)
            permitted = max(
                tolerance.abs_tolerance,
                tolerance.rel_tolerance
                * max(abs(expected_decimal), abs(actual_decimal)),
            )
            if difference > permitted:
                mismatches.append(
                    f"{location}: expected {expected!r}, got {actual!r}, "
                    f"difference {difference} > tolerance {permitted}"
                )
            return
        if type(expected) is not type(actual) or expected != actual:
            mismatches.append(f"{location}: expected {expected!r}, got {actual!r}")

    @staticmethod
    def _index_by_key(
        rows: list[dict[str, Any]], key_columns: list[str]
    ) -> tuple[dict[tuple[Any, ...], dict[str, Any]], str | None]:
        indexed: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            key = tuple(row[column] for column in key_columns)
            if key in indexed:
                return {}, f"duplicate_business_key:{key!r}"
            indexed[key] = row
        return indexed, None

    @staticmethod
    def _stable_key(key: tuple[Any, ...]) -> tuple[str, ...]:
        return tuple(f"{type(item).__name__}:{item!r}" for item in key)

    @classmethod
    def _stable_keys(cls, mapping: dict[tuple[Any, ...], Any]) -> list[tuple[Any, ...]]:
        return sorted(mapping, key=cls._stable_key)

    @staticmethod
    def _is_numeric(value: Any) -> bool:
        return isinstance(value, (Number, Decimal)) and not isinstance(value, bool)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        try:
            converted = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return converted if converted.is_finite() else None

    @staticmethod
    def _failure(oracle_key: str, code: str, detail: str | None = None) -> OracleEvaluation:
        return OracleEvaluation(
            oracle_key=oracle_key,
            passed=False,
            code=code,
            mismatches=[detail or code],
        )
