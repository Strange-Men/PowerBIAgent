"""Deterministic sales-report data and ReportSpec assembly.

Business values are projected from verified facts only.  QueryResult objects
are used to prove the binding and completeness of each VerifiedFactSet; this
module never re-aggregates rows or accepts an expected/oracle value.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.facts.verified import (
    FactType,
    VerifiedFact,
    VerifiedFactSet,
    VerifiedFactSetBuilder,
)
from backend.app.report.contracts import ReportDataPlan, ReportQueryShape
from backend.app.schemas.data_contracts import (
    KPISpec,
    QueryResult,
    ReportSpec,
    TableSpec,
)


SALES_REPORT_QUERY_KEYS = (
    "total_sales",
    "total_quantity",
    "sales_by_category",
    "top_products",
)


class SalesReportAssemblyError(ValueError):
    """Fail-closed deterministic report assembly error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _validate_business_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("sales_report_value_not_numeric")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("sales_report_value_not_finite")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("sales_report_value_not_finite")
    return value


class CategorySalesRow(BaseModel):
    category: str = Field(..., min_length=1)
    total_sales: int | float | Decimal

    model_config = ConfigDict(frozen=True)

    @field_validator("total_sales")
    @classmethod
    def validate_total_sales(cls, value: Any) -> Any:
        return _validate_business_number(value)


class TopProductRow(BaseModel):
    result_position: int = Field(..., ge=1)
    product: str = Field(..., min_length=1)
    total_sales: int | float | Decimal

    model_config = ConfigDict(frozen=True)

    @field_validator("total_sales")
    @classmethod
    def validate_total_sales(cls, value: Any) -> Any:
        return _validate_business_number(value)


class SalesReportData(BaseModel):
    """The sole structured business-data input to the fixed sales renderer."""

    template_key: str
    contract_version: str
    semantic_model_key: str
    schema_fingerprint: str
    total_sales: int | float | Decimal
    total_quantity: int | float | Decimal
    category_sales: tuple[CategorySalesRow, ...]
    top_products: tuple[TopProductRow, ...]
    query_result_ids: tuple[str, ...]
    verified_fact_set_ids: tuple[str, ...]
    source_mode: str
    generated_at: datetime

    model_config = ConfigDict(frozen=True)

    @field_validator("total_sales", "total_quantity")
    @classmethod
    def validate_business_number(cls, value: Any) -> Any:
        return _validate_business_number(value)


class SalesReportDataAssembler:
    """Bind four QueryResults to four complete, untampered VerifiedFactSets."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build(
        self,
        plan: ReportDataPlan,
        query_results: Mapping[str, QueryResult],
        verified_fact_sets: Mapping[str, VerifiedFactSet],
    ) -> SalesReportData:
        if plan.template_key != "sales_report":
            raise SalesReportAssemblyError("sales_report_template_required")
        plan_keys = tuple(item.requirement_key for item in plan.queries)
        if plan_keys != SALES_REPORT_QUERY_KEYS:
            raise SalesReportAssemblyError("sales_report_query_plan_mismatch")
        if set(query_results) != set(SALES_REPORT_QUERY_KEYS):
            raise SalesReportAssemblyError("sales_report_query_result_set_incomplete")
        if set(verified_fact_sets) != set(SALES_REPORT_QUERY_KEYS):
            raise SalesReportAssemblyError("sales_report_fact_set_incomplete")

        source_modes: set[str] = set()
        result_ids: list[str] = []
        fact_set_ids: list[str] = []
        validated_facts: dict[str, VerifiedFactSet] = {}

        for query in plan.queries:
            key = query.requirement_key
            result = query_results[key]
            facts = verified_fact_sets[key]
            self._validate_pair(plan, query.shape, query.query_plan, result, facts)
            source_modes.add(result.source_mode)
            result_ids.append(result.result_id)
            fact_set_ids.append(facts.fact_set_id)
            validated_facts[key] = facts

        if len(source_modes) != 1 or source_modes.pop() not in {"mock", "real"}:
            raise SalesReportAssemblyError("sales_report_source_mode_mixed_or_invalid")
        source_mode = query_results[SALES_REPORT_QUERY_KEYS[0]].source_mode
        if len(set(result_ids)) != len(result_ids):
            raise SalesReportAssemblyError("sales_report_query_result_id_reused")
        if len(set(fact_set_ids)) != len(fact_set_ids):
            raise SalesReportAssemblyError("sales_report_fact_set_id_reused")

        total_sales = self._scalar_value(
            validated_facts["total_sales"], "Total Sales"
        )
        total_quantity = self._scalar_value(
            validated_facts["total_quantity"], "Total Quantity"
        )
        category_sales = self._category_rows(
            validated_facts["sales_by_category"]
        )
        top_products = self._top_product_rows(
            validated_facts["top_products"]
        )

        generated_at = self._clock()
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        return SalesReportData(
            template_key=plan.template_key,
            contract_version=plan.contract_version,
            semantic_model_key=plan.semantic_model_key,
            schema_fingerprint=plan.schema_fingerprint,
            total_sales=total_sales,
            total_quantity=total_quantity,
            category_sales=category_sales,
            top_products=top_products,
            query_result_ids=tuple(result_ids),
            verified_fact_set_ids=tuple(fact_set_ids),
            source_mode=source_mode,
            generated_at=generated_at,
        )

    @staticmethod
    def _validate_pair(
        plan: ReportDataPlan,
        shape: ReportQueryShape,
        query_plan: Any,
        result: QueryResult,
        facts: VerifiedFactSet,
    ) -> None:
        if result.error is not None:
            raise SalesReportAssemblyError("sales_report_query_result_has_error")
        if result.semantic_model_key != plan.semantic_model_key:
            raise SalesReportAssemblyError("sales_report_query_result_model_mismatch")
        if result.source_mode not in {"mock", "real"}:
            raise SalesReportAssemblyError("sales_report_source_mode_invalid")
        if result.row_count == 0:
            raise SalesReportAssemblyError("sales_report_required_query_empty")
        if shape == ReportQueryShape.SCALAR and result.row_count != 1:
            raise SalesReportAssemblyError("sales_report_scalar_shape_invalid")
        if facts.result_id != result.result_id:
            raise SalesReportAssemblyError("sales_report_fact_result_binding_mismatch")
        if facts.semantic_model_key != result.semantic_model_key:
            raise SalesReportAssemblyError("sales_report_fact_model_mismatch")
        if facts.source_mode != result.source_mode:
            raise SalesReportAssemblyError("sales_report_fact_source_mode_mismatch")
        if facts.empty or facts.row_count != result.row_count:
            raise SalesReportAssemblyError("sales_report_fact_row_binding_mismatch")
        if facts.result_columns != result.columns:
            raise SalesReportAssemblyError("sales_report_fact_column_binding_mismatch")

        try:
            rebuilt = VerifiedFactSetBuilder().build(query_plan, result)
        except Exception as exc:
            raise SalesReportAssemblyError("sales_report_fact_rebuild_failed") from exc
        if facts != rebuilt:
            raise SalesReportAssemblyError("sales_report_fact_set_tampered")

    @staticmethod
    def _scalar_value(facts: VerifiedFactSet, measure: str) -> Any:
        candidates = facts.by_type(FactType.SCALAR_METRIC)
        if len(candidates) != 1 or candidates[0].measure != measure:
            raise SalesReportAssemblyError("sales_report_scalar_fact_invalid")
        return _validate_business_number(candidates[0].value)

    @staticmethod
    def _ordered_grouped_facts(facts: VerifiedFactSet) -> list[VerifiedFact]:
        grouped = facts.by_type(FactType.GROUPED_METRIC)
        if len(grouped) != facts.row_count:
            raise SalesReportAssemblyError("sales_report_grouped_fact_count_invalid")
        by_row: dict[int, VerifiedFact] = {}
        for item in grouped:
            if len(item.source_rows) != 1 or item.source_rows[0] in by_row:
                raise SalesReportAssemblyError("sales_report_grouped_fact_order_invalid")
            by_row[item.source_rows[0]] = item
        if tuple(sorted(by_row)) != tuple(range(facts.row_count)):
            raise SalesReportAssemblyError("sales_report_grouped_fact_order_invalid")
        return [by_row[index] for index in range(facts.row_count)]

    @classmethod
    def _category_rows(
        cls, facts: VerifiedFactSet
    ) -> tuple[CategorySalesRow, ...]:
        rows: list[CategorySalesRow] = []
        for item in cls._ordered_grouped_facts(facts):
            if item.measure != "Total Sales" or set(item.dimensions) != {"Category"}:
                raise SalesReportAssemblyError("sales_report_category_fact_invalid")
            rows.append(CategorySalesRow(
                category=str(item.dimensions["Category"]),
                total_sales=item.value,
            ))
        return tuple(rows)

    @classmethod
    def _top_product_rows(
        cls, facts: VerifiedFactSet
    ) -> tuple[TopProductRow, ...]:
        grouped = cls._ordered_grouped_facts(facts)
        ranking = facts.by_type(FactType.RANKING)
        if len(ranking) != 1:
            raise SalesReportAssemblyError("sales_report_topn_fact_invalid")
        ordered = ranking[0]
        if (
            ordered.measure != "Total Sales"
            or ordered.value.get("top_n") != 5
            or ordered.value.get("direction") != "desc"
            or ordered.value.get("position_semantics") != "query_result_order"
            or len(ordered.values) != facts.row_count
        ):
            raise SalesReportAssemblyError("sales_report_topn_fact_invalid")

        rows: list[TopProductRow] = []
        for index, (ranking_item, grouped_item) in enumerate(
            zip(ordered.values, grouped), start=1
        ):
            if (
                ranking_item.get("result_position") != index
                or set(ranking_item.get("dimensions", {})) != {"Product"}
                or grouped_item.measure != "Total Sales"
                or set(grouped_item.dimensions) != {"Product"}
                or ranking_item.get("dimensions") != grouped_item.dimensions
                or ranking_item.get("value") != grouped_item.value
            ):
                raise SalesReportAssemblyError("sales_report_topn_order_forged")
            rows.append(TopProductRow(
                result_position=index,
                product=str(ranking_item["dimensions"]["Product"]),
                total_sales=ranking_item["value"],
            ))
        return tuple(rows)


class SalesReportSpecBuilder:
    """Create the one fixed production ReportSpec from SalesReportData."""

    def build(self, data: SalesReportData) -> ReportSpec:
        if data.template_key != "sales_report":
            raise SalesReportAssemblyError("sales_report_template_required")
        if len(data.query_result_ids) != 4 or len(data.verified_fact_set_ids) != 4:
            raise SalesReportAssemblyError("sales_report_provenance_incomplete")
        return ReportSpec(
            title="销售分析报表",
            template_key="sales_report",
            summary="",
            kpis=[
                KPISpec(
                    name="总销售额",
                    value=data.total_sales,
                    format="currency",
                    field="Total Sales",
                ),
                KPISpec(
                    name="总销量",
                    value=data.total_quantity,
                    format="number",
                    field="Total Quantity",
                ),
            ],
            charts=[],
            tables=[
                TableSpec(
                    title="按类别销售额",
                    columns=["Category", "Total Sales"],
                    rows=[
                        [item.category, item.total_sales]
                        for item in data.category_sales
                    ],
                ),
                TableSpec(
                    title="Top 5 产品销售额",
                    columns=["序号", "Product", "Total Sales"],
                    rows=[
                        [item.result_position, item.product, item.total_sales]
                        for item in data.top_products
                    ],
                ),
            ],
            insights=[],
            data_source=data.semantic_model_key,
            filters=[],
            generated_at=data.generated_at,
            source_mode=data.source_mode,
            contract_version=data.contract_version,
            semantic_model_key=data.semantic_model_key,
            schema_fingerprint=data.schema_fingerprint,
            query_result_ids=list(data.query_result_ids),
            verified_fact_set_ids=list(data.verified_fact_set_ids),
        )
