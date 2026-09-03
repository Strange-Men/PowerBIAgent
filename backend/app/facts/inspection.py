"""Deterministic semantic inspection between QueryResult and VerifiedFactSet."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult, QueryShape


class ResultSemanticInspectionError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ResultSemanticInspection(BaseModel):
    passed: bool = True
    shape: QueryShape
    row_count: int
    canonical_order_preserved: bool = True
    filters_preserved: bool = True
    time_preserved: bool = True
    distinct_preserved: bool = True
    scope_lineage_hash: str

    model_config = ConfigDict(frozen=True)


class ResultSemanticInspectionGate:
    """Inspect result shape/order/scope without repairing or reordering facts."""

    def inspect(
        self,
        plan: CanonicalQueryPlan,
        result: QueryResult,
        *,
        dax_semantic_verified: bool = True,
    ) -> ResultSemanticInspection:
        if not dax_semantic_verified:
            self._fail("result_scope_dax_verification_missing")
        if result.error is not None:
            self._fail("result_inspection_query_error")
        if plan.semantic_model_key != result.semantic_model_key:
            self._fail("result_inspection_model_mismatch")
        shape = plan.query_shape or QueryShape.SCALAR
        if shape == QueryShape.RANKING:
            self._inspect_ranking(plan, result)
        if shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}:
            self._inspect_trend(plan, result)
        if shape == QueryShape.ENTITY_LIST:
            self._inspect_entities(plan, result)
        lineage = hashlib.sha256(json.dumps({
            "plan": plan.model_dump(mode="json"),
            "result_id": result.result_id,
            "semantic_model_key": result.semantic_model_key,
            "source_mode": result.source_mode,
            "request_id": result.request_id,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ResultSemanticInspection(
            shape=shape,
            row_count=result.row_count,
            scope_lineage_hash=lineage,
        )

    def _inspect_ranking(self, plan: CanonicalQueryPlan, result: QueryResult) -> None:
        if plan.top_n is None or plan.sort is None or not plan.measures:
            self._fail("result_ranking_plan_incomplete")
        if result.truncated:
            self._fail("result_ranking_truncated")
        if plan.top_n == 1 and result.row_count != 1:
            self._fail("result_ranking_top1_row_count_invalid")
        if result.row_count > plan.top_n:
            self._fail("result_ranking_row_count_exceeds_top_n")
        measure_index = self._field_index(result.columns, plan.measures[0])
        values = [self._number(row[measure_index]) for row in result.rows]
        pairs = zip(values, values[1:])
        ordered = (
            all(left >= right for left, right in pairs)
            if plan.sort == "desc"
            else all(left <= right for left, right in pairs)
        )
        if not ordered:
            self._fail("result_ranking_order_mismatch")
        dimension_indexes = [
            self._field_index(result.columns, dimension)
            for dimension in plan.dimensions
        ]
        for index, (left, right) in enumerate(zip(values, values[1:])):
            if left != right:
                continue
            left_key = tuple(
                self._stable_order_key(result.rows[index][field_index])
                for field_index in dimension_indexes
            )
            right_key = tuple(
                self._stable_order_key(result.rows[index + 1][field_index])
                for field_index in dimension_indexes
            )
            if left_key > right_key:
                self._fail("result_ranking_tiebreak_order_mismatch")

    def _inspect_trend(self, plan: CanonicalQueryPlan, result: QueryResult) -> None:
        if not plan.dimensions:
            self._fail("result_trend_dimension_missing")
        temporal_index = self._field_index(result.columns, plan.dimensions[0])
        values = [self._date_value(row[temporal_index]) for row in result.rows]
        if any(left > right for left, right in zip(values, values[1:])):
            self._fail("result_trend_order_mismatch")
        if plan.query_shape == QueryShape.BOUNDED_TREND:
            if plan.time_range is None:
                self._fail("result_trend_requested_range_missing")
            if any(
                value < plan.time_range.start_date or value > plan.time_range.end_date
                for value in values
            ):
                self._fail("result_trend_outside_requested_range")

    def _inspect_entities(self, plan: CanonicalQueryPlan, result: QueryResult) -> None:
        if not plan.dimensions:
            self._fail("result_entity_list_dimension_missing")
        indexes = [self._field_index(result.columns, field) for field in plan.dimensions]
        identities = [tuple(self._stable(row[index]) for index in indexes) for row in result.rows]
        if len(set(identities)) != len(identities):
            self._fail("result_entity_list_duplicate")

    @staticmethod
    def _field_index(columns: list[str], canonical: str) -> int:
        matches = []
        for index, column in enumerate(columns):
            match = re.search(r"\[([^\]]+)\]\s*$", column)
            if (match.group(1) if match else column) == canonical:
                matches.append(index)
        if len(matches) != 1:
            raise ResultSemanticInspectionError("result_inspection_field_missing_or_ambiguous")
        return matches[0]

    @staticmethod
    def _number(value: Any) -> Decimal:
        if isinstance(value, bool) or value is None:
            raise ResultSemanticInspectionError("result_ranking_metric_not_numeric")
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ResultSemanticInspectionError("result_ranking_metric_not_numeric") from exc
        if not parsed.is_finite() or (isinstance(value, float) and not math.isfinite(value)):
            raise ResultSemanticInspectionError("result_ranking_metric_not_numeric")
        return parsed

    @staticmethod
    def _date_value(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            text = value.strip()
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                match = re.fullmatch(r"(\d{4})[年/-](\d{1,2})(?:月|$)", text)
                if match:
                    return date(int(match.group(1)), int(match.group(2)), 1)
        raise ResultSemanticInspectionError("result_trend_temporal_value_invalid")

    @staticmethod
    def _stable(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @classmethod
    def _stable_order_key(cls, value: Any) -> str:
        """Mirror the builder's deterministic ASC dimension tie-break."""
        return cls._stable(value).casefold()

    @staticmethod
    def _fail(code: str) -> None:
        raise ResultSemanticInspectionError(code)
