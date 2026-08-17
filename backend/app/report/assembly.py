"""Deterministic adaptive report data and ReportSpec assembly.

Business values are projected from verified facts only.  QueryResult objects
are used to prove the binding and completeness of each VerifiedFactSet; this
module never re-aggregates rows, never accepts an expected/oracle value, and
never invents numbers.  The only display-side computation is the deterministic
ordering of already-verified grouped time points (display order, never new
business values) and the fixed KPI labels of the design system.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
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
from backend.app.report.contracts import (
    ReportDataPlan,
    ReportQueryShape,
)
from backend.app.report.policy import VisualizationPolicy
from backend.app.schemas.data_contracts import (
    ChartSpec,
    KPISpec,
    QueryResult,
    ReportSpec,
)


SALES_REPORT_TEMPLATE_KEY = "sales_report"


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


# ── Fixed KPI registry (label / measure / presentation format) ────────────
# Only these scalar requirement keys may appear as KPI cards.

class KpiDefinition(BaseModel):
    requirement_key: str
    label: str
    measure: str
    format: str

    model_config = ConfigDict(frozen=True)


KPI_DEFINITIONS: Mapping[str, KpiDefinition] = {
    "total_sales": KpiDefinition(
        requirement_key="total_sales", label="总销售额",
        measure="Total Sales", format="currency",
    ),
    "total_quantity": KpiDefinition(
        requirement_key="total_quantity", label="总销量",
        measure="Total Quantity", format="number",
    ),
    "total_orders": KpiDefinition(
        requirement_key="total_orders", label="总订单数",
        measure="Total Orders", format="number",
    ),
    "average_order_value": KpiDefinition(
        requirement_key="average_order_value", label="平均订单金额",
        measure="Average Order Value", format="currency",
    ),
}


class KpiValue(BaseModel):
    requirement_key: str
    label: str
    measure: str
    value: int | float | Decimal
    format: str

    model_config = ConfigDict(frozen=True)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        return _validate_business_number(value)


class TrendPoint(BaseModel):
    period: str = Field(..., min_length=1)
    value: int | float | Decimal

    model_config = ConfigDict(frozen=True)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        return _validate_business_number(value)


class GroupedValue(BaseModel):
    label: str = Field(..., min_length=1)
    value: int | float | Decimal

    model_config = ConfigDict(frozen=True)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        return _validate_business_number(value)


class TopNValue(BaseModel):
    result_position: int = Field(..., ge=1)
    label: str = Field(..., min_length=1)
    value: int | float | Decimal

    model_config = ConfigDict(frozen=True)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        return _validate_business_number(value)


class SectionProjection(BaseModel):
    """Typed projection of one verified query into report-presentable rows."""

    requirement_key: str
    shape: ReportQueryShape
    measure: str
    dimension: str = ""
    kind: str  # trend | grouped | top_n
    values: list[Any] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class SalesReportData(BaseModel):
    """The sole structured business-data input to the adaptive renderer."""

    template_key: str
    contract_version: str
    semantic_model_key: str
    schema_fingerprint: str
    kpis: tuple[KpiValue, ...]
    sections: tuple[SectionProjection, ...]
    query_result_ids: tuple[str, ...]
    verified_fact_set_ids: tuple[str, ...]
    source_mode: str
    generated_at: datetime

    model_config = ConfigDict(frozen=True)


class SalesReportDataAssembler:
    """Bind resolved QueryResults to complete, untampered VerifiedFactSets."""

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
        if plan.template_key != SALES_REPORT_TEMPLATE_KEY:
            raise SalesReportAssemblyError("sales_report_template_required")
        plan_keys = tuple(item.requirement_key for item in plan.queries)
        if len(plan_keys) != len(set(plan_keys)):
            raise SalesReportAssemblyError("sales_report_query_plan_duplicate")
        if set(query_results) != set(plan_keys):
            raise SalesReportAssemblyError("sales_report_query_result_set_incomplete")
        if set(verified_fact_sets) != set(plan_keys):
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
        source_mode = query_results[plan_keys[0]].source_mode
        if len(set(result_ids)) != len(result_ids):
            raise SalesReportAssemblyError("sales_report_query_result_id_reused")
        if len(set(fact_set_ids)) != len(fact_set_ids):
            raise SalesReportAssemblyError("sales_report_fact_set_id_reused")

        kpis: list[KpiValue] = []
        sections: list[SectionProjection] = []
        for query in plan.queries:
            key = query.requirement_key
            facts = validated_facts[key]
            definition = KPI_DEFINITIONS.get(key)
            if query.shape == ReportQueryShape.SCALAR:
                if definition is None:
                    raise SalesReportAssemblyError(
                        "sales_report_scalar_requirement_not_registered"
                    )
                kpis.append(self._kpi_value(facts, definition))
                continue
            sections.append(self._projection(query, facts))
        if not kpis and not sections:
            raise SalesReportAssemblyError("sales_report_no_resolved_sections")

        generated_at = self._clock()
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        return SalesReportData(
            template_key=plan.template_key,
            contract_version=plan.contract_version,
            semantic_model_key=plan.semantic_model_key,
            schema_fingerprint=plan.schema_fingerprint,
            kpis=tuple(kpis),
            sections=tuple(sections),
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
    def _kpi_value(facts: VerifiedFactSet, definition: KpiDefinition) -> KpiValue:
        candidates = facts.by_type(FactType.SCALAR_METRIC)
        if len(candidates) != 1 or candidates[0].measure != definition.measure:
            raise SalesReportAssemblyError("sales_report_scalar_fact_invalid")
        return KpiValue(
            requirement_key=definition.requirement_key,
            label=definition.label,
            measure=definition.measure,
            value=_validate_business_number(candidates[0].value),
            format=definition.format,
        )

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
    def _projection(
        cls, query: Any, facts: VerifiedFactSet
    ) -> SectionProjection:
        requirement = query.requirement_key
        measure = query.query_plan.measures[0]
        dimension = query.query_plan.dimensions[0]
        dimension_tables = query.query_plan.dimension_tables or {}
        grouped = cls._ordered_grouped_facts(facts)

        if query.shape == ReportQueryShape.ORDERED_TOP_N:
            return SectionProjection(
                requirement_key=requirement,
                shape=ReportQueryShape.ORDERED_TOP_N,
                measure=measure,
                dimension=dimension,
                kind="top_n",
                values=cls._top_n_values(
                    facts, grouped, query, measure, dimension
                ),
            )

        rows: list[VerifiedFact] = []
        for item in grouped:
            if (
                item.measure != measure
                or set(item.dimensions) != {dimension}
                or item.dimensions[dimension] is None
            ):
                raise SalesReportAssemblyError(
                    "sales_report_grouped_fact_invalid"
                )
            rows.append(item)

        if query.query_plan.dimension_order is not None:
            # Display-only deterministic ordering of verified time points.
            ordered = sorted(
                rows,
                key=lambda item: cls._sort_key(item.dimensions[dimension]),
            )
            return SectionProjection(
                requirement_key=requirement,
                shape=ReportQueryShape.GROUPED,
                measure=measure,
                dimension=dimension,
                kind="trend",
                values=[
                    TrendPoint(
                        period=cls._period_label(item.dimensions[dimension]),
                        value=item.value,
                    )
                    for item in ordered
                ],
            )
        return SectionProjection(
            requirement_key=requirement,
            shape=ReportQueryShape.GROUPED,
            measure=measure,
            dimension=dimension,
            kind="grouped",
            values=[
                GroupedValue(
                    label=str(item.dimensions[dimension]),
                    value=item.value,
                )
                for item in rows
            ],
        )

    @classmethod
    def _top_n_values(
        cls,
        facts: VerifiedFactSet,
        grouped: list[VerifiedFact],
        query: Any,
        measure: str,
        dimension: str,
    ) -> list[TopNValue]:
        ranking = facts.by_type(FactType.RANKING)
        if len(ranking) != 1:
            raise SalesReportAssemblyError("sales_report_topn_fact_invalid")
        ordered = ranking[0]
        if (
            ordered.measure != measure
            or ordered.value.get("top_n") != query.query_plan.top_n
            or ordered.value.get("direction") != query.query_plan.sort
            or ordered.value.get("position_semantics") != "query_result_order"
            or len(ordered.values) != facts.row_count
        ):
            raise SalesReportAssemblyError("sales_report_topn_fact_invalid")

        rows: list[TopNValue] = []
        for index, (ranking_item, grouped_item) in enumerate(
            zip(ordered.values, grouped), start=1
        ):
            if (
                ranking_item.get("result_position") != index
                or set(ranking_item.get("dimensions", {})) != {dimension}
                or grouped_item.measure != measure
                or set(grouped_item.dimensions) != {dimension}
                or ranking_item.get("dimensions") != grouped_item.dimensions
                or ranking_item.get("value") != grouped_item.value
                or ranking_item.get("dimensions", {}).get(dimension) is None
            ):
                raise SalesReportAssemblyError("sales_report_topn_order_forged")
            rows.append(TopNValue(
                result_position=index,
                label=str(ranking_item["dimensions"][dimension]),
                value=ranking_item["value"],
            ))
        return rows

    @staticmethod
    def _sort_key(value: Any) -> tuple[int, str]:
        """Orderable, type-safe sort key for verified dimension values."""
        if isinstance(value, (datetime, date)):
            return (0, value.isoformat())
        return (1, str(value))

    @staticmethod
    def _period_label(value: Any) -> str:
        if isinstance(value, (datetime, date)):
            rendered = value.isoformat()
        else:
            rendered = str(value)
        return rendered[:7] if len(rendered) >= 7 else rendered


class SalesReportSpecBuilder:
    """Create the adaptive production ReportSpec from verified report data.

    Visualization choice is delegated to the deterministic VisualizationPolicy
    (business role + data shape/cardinality), never to an LLM.
    """

    def __init__(
        self,
        visualization_policy: VisualizationPolicy | None = None,
    ) -> None:
        self._visualization = visualization_policy or VisualizationPolicy()

    def build(self, data: SalesReportData) -> ReportSpec:
        if data.template_key != SALES_REPORT_TEMPLATE_KEY:
            raise SalesReportAssemblyError("sales_report_template_required")
        if not data.query_result_ids or not data.verified_fact_set_ids:
            raise SalesReportAssemblyError("sales_report_provenance_incomplete")
        if len(data.query_result_ids) != len(data.verified_fact_set_ids):
            raise SalesReportAssemblyError("sales_report_provenance_incomplete")

        kpis = [
            KPISpec(
                name=item.label,
                value=item.value,
                format=item.format,
                field=item.measure,
            )
            for item in data.kpis
        ]
        charts: list[ChartSpec] = []
        for section in data.sections:
            rows = section.values
            row_count = len(rows)
            role = self._section_key_for_requirement(section.requirement_key)
            visual = self._visualization.choose(role, row_count=row_count)
            charts.append(ChartSpec(
                type="bar",
                title=visual.title,
                x_field=section.dimension,
                y_field=section.measure,
                visual_type=visual.visual_type.value,
                business_role=role.value,
                series=[
                    {
                        "label": self._series_label(item),
                        "value": self._series_value(item),
                        # Only verified TopN results carry a result_position;
                        # grouped rows never claim a rank (ERR-264-001).
                        "position": (
                            item.result_position
                            if section.kind == "top_n"
                            else None
                        ),
                    }
                    for index, item in enumerate(rows)
                ],
                layout_hint=visual.layout_hint,
            ))
        return ReportSpec(
            title="销售分析报表",
            template_key=SALES_REPORT_TEMPLATE_KEY,
            summary="",
            kpis=kpis,
            charts=charts,
            tables=[],
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

    @staticmethod
    def _section_key_for_requirement(requirement_key: str):
        from backend.app.report.capability import (
            SECTION_REQUIREMENTS,
            SectionKey,
        )

        matches = [
            key for key, keys in SECTION_REQUIREMENTS.items()
            if requirement_key in keys
        ]
        if len(matches) != 1:
            raise SalesReportAssemblyError("sales_report_section_binding_invalid")
        return matches[0]

    @staticmethod
    def _series_label(item: Any) -> str:
        if isinstance(item, TrendPoint):
            return item.period
        return item.label

    @staticmethod
    def _series_value(item: Any) -> Any:
        return item.value
