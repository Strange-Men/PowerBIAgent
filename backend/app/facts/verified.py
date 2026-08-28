"""Deterministic factual authority derived from plan + QueryResult only."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.data_contracts import (
    AnswerSpec,
    CanonicalQueryPlan,
    ChartSpec,
    KPISpec,
    QueryResult,
    ReportSpec,
    StructuredFilter,
    TableSpec,
    TimeRangeSpec,
)


class FactType(str, Enum):
    ENTITY_VALUE = "entity_value"
    SCALAR_METRIC = "scalar_metric"
    GROUPED_METRIC = "grouped_metric"
    RANKING = "ranking"
    MAXIMUM = "maximum"
    MINIMUM = "minimum"
    APPLIED_FILTER = "applied_filter"
    APPLIED_TIME_RANGE = "applied_time_range"
    RESULT_METADATA = "result_metadata"


class FactProvenance(BaseModel):
    result_id: str
    semantic_model_key: str
    source_mode: str
    source_fields: list[str] = Field(default_factory=list)
    source_rows: list[int] = Field(default_factory=list)
    operation: str
    plan_semantics: dict[str, Any]

    model_config = ConfigDict(frozen=True)


class VerifiedFact(BaseModel):
    fact_id: str
    fact_type: FactType
    value: Any = None
    values: list[Any] = Field(default_factory=list)
    source_fields: list[str] = Field(default_factory=list)
    source_rows: list[int] = Field(default_factory=list)
    operation: str
    measure: str | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    filters: list[StructuredFilter] = Field(default_factory=list)
    time_range: TimeRangeSpec | None = None
    provenance: FactProvenance

    model_config = ConfigDict(frozen=True)


class VerifiedFactSet(BaseModel):
    fact_set_id: str
    result_id: str
    semantic_model_key: str
    source_mode: str
    row_count: int
    truncated: bool
    empty: bool
    result_columns: list[str]
    facts: list[VerifiedFact]

    model_config = ConfigDict(frozen=True)

    def by_type(self, fact_type: FactType) -> list[VerifiedFact]:
        return [item for item in self.facts if item.fact_type == fact_type]

    def get(self, fact_id: str) -> VerifiedFact | None:
        return next((item for item in self.facts if item.fact_id == fact_id), None)


class FactVerificationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class VerifiedFactSetBuilder:
    """Build the complete claimable fact boundary without language inference."""

    def build(
        self, plan: CanonicalQueryPlan, result: QueryResult
    ) -> VerifiedFactSet:
        if result.error is not None:
            raise FactVerificationError("fact_query_result_has_error")
        if plan.semantic_model_key != result.semantic_model_key:
            raise FactVerificationError("fact_model_mismatch")
        if result.row_count != len(result.rows):
            raise FactVerificationError("fact_row_count_mismatch")

        column_map = self._column_map(result.columns)
        dimension_fields = [self._require_field(column_map, name) for name in plan.dimensions]
        measure_fields = [self._require_field(column_map, name) for name in plan.measures]
        if not plan.dimensions and result.row_count > 1:
            raise FactVerificationError("fact_scalar_row_count_invalid")

        fact_set_id = self._fact_set_id(plan, result)
        plan_semantics = plan.model_dump(mode="json")
        facts: list[VerifiedFact] = []

        for row_index, row in enumerate(result.rows):
            dimensions = {
                name: row[result.columns.index(source)]
                for name, source in zip(plan.dimensions, dimension_fields)
            }
            for measure, source in zip(plan.measures, measure_fields):
                value = row[result.columns.index(source)]
                fact_type = (
                    FactType.GROUPED_METRIC
                    if plan.dimensions else FactType.SCALAR_METRIC
                )
                facts.append(self._fact(
                    fact_set_id,
                    len(facts),
                    fact_type,
                    value=value,
                    source_fields=[*dimension_fields, source],
                    source_rows=[row_index],
                    operation="direct_result_projection",
                    measure=measure,
                    dimensions=dimensions,
                    filters=plan.filters,
                    time_range=plan.time_range,
                    result=result,
                    plan_semantics=plan_semantics,
                ))
            if plan.dimensions and not plan.measures:
                facts.append(self._fact(
                    fact_set_id,
                    len(facts),
                    FactType.ENTITY_VALUE,
                    value=dimensions,
                    source_fields=list(dimension_fields),
                    source_rows=[row_index],
                    operation="direct_distinct_entity_projection",
                    dimensions=dimensions,
                    filters=plan.filters,
                    time_range=plan.time_range,
                    result=result,
                    plan_semantics=plan_semantics,
                ))

        if plan.top_n is not None and result.rows:
            ordered = []
            for row_index, row in enumerate(result.rows):
                ordered.append({
                    # QueryResult order is directly observable.  A strict
                    # business rank is not: equal measure values can tie and a
                    # truncated result may omit additional boundary ties.
                    "result_position": row_index + 1,
                    "dimensions": {
                        name: row[result.columns.index(source)]
                        for name, source in zip(plan.dimensions, dimension_fields)
                    },
                    "measure": plan.measures[0],
                    "value": row[result.columns.index(measure_fields[0])],
                })
            facts.append(self._fact(
                fact_set_id,
                len(facts),
                FactType.RANKING,
                value={
                    "top_n": plan.top_n,
                    "direction": plan.sort,
                    "measure": plan.measures[0],
                    "position_semantics": "query_result_order",
                    "complete": not result.truncated,
                },
                values=ordered,
                source_fields=[*dimension_fields, measure_fields[0]],
                source_rows=list(range(result.row_count)),
                operation="ordered_topn_result_projection",
                measure=plan.measures[0],
                filters=plan.filters,
                time_range=plan.time_range,
                result=result,
                plan_semantics=plan_semantics,
            ))

        if plan.dimensions and result.rows and not result.truncated:
            for measure, source in zip(plan.measures, measure_fields):
                values = [
                    (index, row[result.columns.index(source)])
                    for index, row in enumerate(result.rows)
                ]
                numeric = [item for item in values if self._is_number(item[1])]
                if len(numeric) != len(values) or not numeric:
                    continue
                for fact_type, selected, operation in (
                    (FactType.MAXIMUM, max(numeric, key=lambda item: item[1]), "result_set_max"),
                    (FactType.MINIMUM, min(numeric, key=lambda item: item[1]), "result_set_min"),
                ):
                    index, value = selected
                    dimensions = {
                        name: result.rows[index][result.columns.index(field)]
                        for name, field in zip(plan.dimensions, dimension_fields)
                    }
                    facts.append(self._fact(
                        fact_set_id,
                        len(facts),
                        fact_type,
                        value=value,
                        source_fields=[*dimension_fields, source],
                        source_rows=[index],
                        operation=operation,
                        measure=measure,
                        dimensions=dimensions,
                        filters=plan.filters,
                        time_range=plan.time_range,
                        result=result,
                        plan_semantics=plan_semantics,
                    ))

        for item in plan.filters:
            facts.append(self._fact(
                fact_set_id,
                len(facts),
                FactType.APPLIED_FILTER,
                value=item.model_dump(mode="json"),
                source_fields=[item.field],
                operation="canonical_plan_filter",
                filters=[item],
                result=result,
                plan_semantics=plan_semantics,
            ))
        if plan.time_range is not None:
            facts.append(self._fact(
                fact_set_id,
                len(facts),
                FactType.APPLIED_TIME_RANGE,
                value=plan.time_range.model_dump(mode="json"),
                source_fields=[plan.time_range.date_field],
                operation="canonical_plan_time_range",
                time_range=plan.time_range,
                result=result,
                plan_semantics=plan_semantics,
            ))
        facts.append(self._fact(
            fact_set_id,
            len(facts),
            FactType.RESULT_METADATA,
            value={
                "row_count": result.row_count,
                "truncated": result.truncated,
                "empty": result.row_count == 0,
            },
            source_fields=list(result.columns),
            source_rows=list(range(result.row_count)),
            operation="query_result_metadata",
            result=result,
            plan_semantics=plan_semantics,
        ))
        return VerifiedFactSet(
            fact_set_id=fact_set_id,
            result_id=result.result_id,
            semantic_model_key=result.semantic_model_key,
            source_mode=result.source_mode,
            row_count=result.row_count,
            truncated=result.truncated,
            empty=result.row_count == 0,
            result_columns=list(result.columns),
            facts=facts,
        )

    @staticmethod
    def _column_map(columns: list[str]) -> dict[str, list[str]]:
        mapped: dict[str, list[str]] = {}
        for column in columns:
            match = re.search(r"\[([^\]]+)\]\s*$", column)
            canonical = match.group(1) if match else column
            mapped.setdefault(canonical, []).append(column)
        return mapped

    @staticmethod
    def _require_field(column_map: dict[str, list[str]], name: str) -> str:
        matches = column_map.get(name, [])
        if not matches:
            raise FactVerificationError("fact_source_field_missing")
        if len(matches) != 1:
            raise FactVerificationError("fact_source_field_ambiguous")
        return matches[0]

    @staticmethod
    def _fact_set_id(plan: CanonicalQueryPlan, result: QueryResult) -> str:
        payload = json.dumps({
            "result_id": result.result_id,
            "plan": plan.model_dump(mode="json"),
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "facts-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _fact(
        fact_set_id: str,
        index: int,
        fact_type: FactType,
        *,
        result: QueryResult,
        plan_semantics: dict[str, Any],
        value: Any = None,
        values: list[Any] | None = None,
        source_fields: list[str] | None = None,
        source_rows: list[int] | None = None,
        operation: str,
        measure: str | None = None,
        dimensions: dict[str, Any] | None = None,
        filters: list[StructuredFilter] | None = None,
        time_range: TimeRangeSpec | None = None,
    ) -> VerifiedFact:
        fact_id = f"{fact_set_id}:{index}:{fact_type.value}"
        source_fields = source_fields or []
        source_rows = source_rows or []
        return VerifiedFact(
            fact_id=fact_id,
            fact_type=fact_type,
            value=value,
            values=values or [],
            source_fields=source_fields,
            source_rows=source_rows,
            operation=operation,
            measure=measure,
            dimensions=dimensions or {},
            filters=filters or [],
            time_range=time_range,
            provenance=FactProvenance(
                result_id=result.result_id,
                semantic_model_key=result.semantic_model_key,
                source_mode=result.source_mode,
                source_fields=source_fields,
                source_rows=source_rows,
                operation=operation,
                plan_semantics=plan_semantics,
            ),
        )

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


class FactBoundedAnswerBuilder:
    def build(
        self,
        plan: CanonicalQueryPlan,
        result: QueryResult,
        facts: VerifiedFactSet,
        *,
        display_bindings: dict[str, Any] | None = None,
        locale: str = "zh-CN",
    ) -> AnswerSpec:
        # Local import avoids making the factual authority module depend on the
        # presentation package during module initialization.
        from backend.app.presentation.formatter import (
            PresentationFormatKind,
            PresentationFormatter,
        )

        formatter = PresentationFormatter(locale=locale)
        bindings = display_bindings or {}
        used: list[VerifiedFact] = []
        parts: list[str] = []
        metrics: dict[str, Any] = {}
        metric_provenance: dict[str, dict[str, str]] = {}
        if facts.empty:
            parts.append("暂无符合条件的数据。")
        elif plan.top_n is not None:
            ranking = facts.by_type(FactType.RANKING)[0]
            used.append(ranking)
            first = ranking.values[0]
            dimension_text = self._dimension_text(
                first["dimensions"],
                ranking.source_fields,
                formatter,
                bindings,
            )
            measure_field = ranking.source_fields[-1]
            measure_label = self._field_label(
                first["measure"], measure_field, bindings
            )
            parts.append(
                f"TopN结果共返回{len(ranking.values)}项；首项为{dimension_text}，"
                f"{measure_label}为{self._format_value(first['value'], measure_field, formatter, bindings)}。"
            )
        elif plan.dimensions and not plan.measures:
            entities = facts.by_type(FactType.ENTITY_VALUE)
            used.extend(entities)
            parts.append(f"共返回{result.row_count}项，完整列表见表格。")
        elif plan.dimensions:
            grouped = facts.by_type(FactType.GROUPED_METRIC)
            primary = [
                item for item in grouped if item.measure == plan.measures[0]
            ]
            if len(primary) == 1:
                item = primary[0]
                used.append(item)
                dimension_text = self._dimension_text(
                    item.dimensions,
                    item.source_fields,
                    formatter,
                    bindings,
                    month=self._is_time_grouped(plan, primary),
                )
                measure_field = item.source_fields[-1]
                parts.append(
                    f"{dimension_text}的{self._field_label(item.measure or measure_field, measure_field, bindings)}"
                    f"为{self._format_value(item.value, measure_field, formatter, bindings)}。"
                )
            elif self._is_time_grouped(plan, primary):
                parts.append(
                    self._trend_summary(
                        plan,
                        facts,
                        primary,
                        used,
                        formatter,
                        bindings,
                    )
                )
            else:
                maximum = next(
                    (
                        item
                        for item in facts.by_type(FactType.MAXIMUM)
                        if item.measure == plan.measures[0]
                    ),
                    None,
                )
                if maximum is not None:
                    used.append(maximum)
                    measure_field = maximum.source_fields[-1]
                    parts.append(
                        f"{self._dimension_text(maximum.dimensions, maximum.source_fields, formatter, bindings)}"
                        f"的{self._field_label(maximum.measure or measure_field, measure_field, bindings)}最高，"
                        f"为{self._format_value(maximum.value, measure_field, formatter, bindings)}。"
                    )
                else:
                    parts.append(f"共返回{result.row_count}项，完整明细见表格。")
        else:
            scalar = facts.by_type(FactType.SCALAR_METRIC)
            used.extend(scalar)
            for item in scalar:
                source_field = item.source_fields[-1]
                parts.append(
                    f"{self._field_label(item.measure or source_field, source_field, bindings)}"
                    f"为{self._format_value(item.value, source_field, formatter, bindings)}。"
                )
                if self._is_number(item.value):
                    metrics[item.measure or "metric"] = item.value
                    metric_provenance[item.measure or "metric"] = {
                        "source_field": item.source_fields[-1],
                        "aggregation": "direct",
                    }

        for item in facts.by_type(FactType.APPLIED_FILTER):
            used.append(item)
            value = item.value
            parts.append(
                f"筛选条件：{value['field']}={formatter.format(value['value'])}。"
            )
        for item in facts.by_type(FactType.APPLIED_TIME_RANGE):
            used.append(item)
            value = item.value
            parts.append(
                f"时间范围：{formatter.format(value['start_date'], PresentationFormatKind.DATE)}"
                f"至{formatter.format(value['end_date'], PresentationFormatKind.DATE)}。"
            )
        metadata = facts.by_type(FactType.RESULT_METADATA)[0]
        used.append(metadata)
        if facts.truncated:
            parts.append("结果已截断，可能不完整。")
        unique_used = list({item.fact_id: item for item in used}.values())
        text = "".join(parts)
        return AnswerSpec(
            answer=text,
            summary=text,
            metrics=metrics,
            evidence={
                "result_id": result.result_id,
                "semantic_model_key": result.semantic_model_key,
                "row_count": result.row_count,
                "source_mode": result.source_mode,
                "verified_fact_set_id": facts.fact_set_id,
                "fact_ids": [item.fact_id for item in unique_used],
                "metric_provenance": metric_provenance,
            },
            filters=list(plan.filters),
            semantic_model_key=result.semantic_model_key,
            source_mode=result.source_mode,
            verified_fact_set_id=facts.fact_set_id,
            fact_ids=[item.fact_id for item in unique_used],
        )

    @staticmethod
    def _field_label(
        canonical_name: str,
        source_field: str,
        bindings: dict[str, Any],
    ) -> str:
        binding = bindings.get(source_field)
        return binding.display_name if binding is not None else canonical_name

    @classmethod
    def _dimension_text(
        cls,
        dimensions: dict[str, Any],
        source_fields: list[str],
        formatter: Any,
        bindings: dict[str, Any],
        *,
        month: bool = False,
    ) -> str:
        from backend.app.presentation.formatter import PresentationFormatKind

        rendered: list[str] = []
        for index, (canonical_name, value) in enumerate(dimensions.items()):
            source_field = source_fields[index]
            label = cls._field_label(canonical_name, source_field, bindings)
            if month:
                display_value = formatter.format(
                    value, PresentationFormatKind.MONTH
                )
            else:
                display_value = cls._format_value(
                    value, source_field, formatter, bindings
                )
            rendered.append(f"{label}{display_value}")
        return "，".join(rendered)

    @staticmethod
    def _format_value(
        value: Any,
        source_field: str,
        formatter: Any,
        bindings: dict[str, Any],
    ) -> str:
        binding = bindings.get(source_field)
        kind = binding.format_kind if binding is not None else None
        return formatter.format(value) if kind is None else formatter.format(value, kind)

    @staticmethod
    def _is_time_grouped(
        plan: CanonicalQueryPlan,
        grouped: list[VerifiedFact],
    ) -> bool:
        dimension_text = " ".join(plan.dimensions).casefold()
        if any(
            token in dimension_text
            for token in ("date", "month", "year", "日期", "月", "年")
        ):
            return True
        if not grouped or not plan.dimensions:
            return False
        values = [item.dimensions.get(plan.dimensions[0]) for item in grouped]
        return all(
            isinstance(value, (date, datetime))
            or (
                isinstance(value, str)
                and len(value) >= 7
                and value[:4].isdigit()
                and value[4] in "-/"
            )
            for value in values
        )

    @classmethod
    def _trend_summary(
        cls,
        plan: CanonicalQueryPlan,
        facts: VerifiedFactSet,
        grouped: list[VerifiedFact],
        used: list[VerifiedFact],
        formatter: Any,
        bindings: dict[str, Any],
    ) -> str:
        maximum = next(
            (
                item
                for item in facts.by_type(FactType.MAXIMUM)
                if item.measure == plan.measures[0]
            ),
            None,
        )
        if maximum is None or not cls._is_number(maximum.value):
            return f"该期间共返回{facts.row_count}项，完整明细见表格。"
        used.append(maximum)
        measure_field = maximum.source_fields[-1]
        measure_label = cls._field_label(
            maximum.measure or measure_field, measure_field, bindings
        )
        peak_index = maximum.source_rows[0]
        summary = (
            f"该期间{measure_label}在"
            f"{cls._dimension_text(maximum.dimensions, maximum.source_fields, formatter, bindings, month=True)}"
            f"达到最高点，为{cls._format_value(maximum.value, measure_field, formatter, bindings)}"
        )
        after_peak = grouped[peak_index + 1 :]
        if after_peak and any(
            cls._is_number(item.value) and item.value < maximum.value
            for item in after_peak
        ):
            summary += "，随后回落"
        if (
            len(grouped) >= 2
            and cls._is_number(grouped[-1].value)
            and cls._is_number(grouped[-2].value)
            and grouped[-1].value > grouped[-2].value
        ):
            used.extend([grouped[-2], grouped[-1]])
            summary += (
                "，并在"
                f"{cls._dimension_text(grouped[-1].dimensions, grouped[-1].source_fields, formatter, bindings, month=True)}"
                "出现回升"
            )
        return summary + "。"

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


class FactBoundedReportBuilder:
    def build(
        self,
        plan: CanonicalQueryPlan,
        result: QueryResult,
        facts: VerifiedFactSet,
    ) -> ReportSpec:
        metric_facts = facts.by_type(FactType.SCALAR_METRIC)
        kpis = [
            KPISpec(
                name=item.measure or item.source_fields[-1],
                value=item.value,
                field=item.source_fields[-1],
            )
            for item in metric_facts
        ]
        charts: list[ChartSpec] = []
        if plan.dimensions and plan.measures and result.rows:
            column_map = VerifiedFactSetBuilder._column_map(result.columns)
            x_field = VerifiedFactSetBuilder._require_field(
                column_map, plan.dimensions[0]
            )
            y_field = VerifiedFactSetBuilder._require_field(
                column_map, plan.measures[0]
            )
            charts.append(ChartSpec(
                type="bar",
                title="查询结果",
                x_field=x_field,
                y_field=y_field,
            ))
        tables = [] if facts.empty else [TableSpec(
            title="查询明细",
            columns=list(result.columns),
            rows=[list(row) for row in result.rows],
        )]
        metadata = facts.by_type(FactType.RESULT_METADATA)[0]
        insights = [f"结果包含 {result.row_count} 行。"]
        if result.truncated:
            insights.append("结果已截断，可能不完整。")
        return ReportSpec(
            title="Power BI 查询报告",
            template_key=plan.requested_template or "",
            summary=f"结果包含 {result.row_count} 行。",
            kpis=kpis,
            charts=charts,
            tables=tables,
            insights=insights,
            data_source=result.semantic_model_key,
            filters=list(plan.filters),
            source_mode=result.source_mode,
            verified_fact_set_id=facts.fact_set_id,
            fact_ids=[item.fact_id for item in facts.facts],
        )


class FactOutputValidator:
    """Validate externally visible factual fields against a FactSet."""

    _NUMBER = re.compile(
        r"(?<![A-Za-z0-9_.])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
    )
    _CAUSAL = ("因为", "导致", "原因", "归因于", "由于")
    _TREND = ("上升", "下降", "增长", "减少", "趋势")

    def validate_answer(
        self, answer: AnswerSpec, facts: VerifiedFactSet
    ) -> list[str]:
        errors = self._validate_binding(
            answer.verified_fact_set_id, answer.fact_ids, facts
        )
        used = [facts.get(item) for item in answer.fact_ids]
        used = [item for item in used if item is not None]
        errors.extend(self._validate_text(answer.answer + " " + answer.summary, used))
        scalar = {
            item.measure: item.value
            for item in used
            if item.fact_type == FactType.SCALAR_METRIC
        }
        for key, value in answer.metrics.items():
            if key not in scalar or scalar[key] != value:
                errors.append("answer_metric_not_in_verified_facts")
        return list(dict.fromkeys(errors))

    def validate_report(
        self, report: ReportSpec, facts: VerifiedFactSet, result: QueryResult
    ) -> list[str]:
        errors = self._validate_binding(
            report.verified_fact_set_id, report.fact_ids, facts
        )
        used = [facts.get(item) for item in report.fact_ids]
        used = [item for item in used if item is not None]
        errors.extend(self._validate_text(
            " ".join([report.summary, *report.insights]), used
        ))
        metric_pairs = {
            (item.source_fields[-1], self._json_value(item.value))
            for item in used
            if item.fact_type == FactType.SCALAR_METRIC and item.source_fields
        }
        for kpi in report.kpis:
            if (kpi.field, self._json_value(kpi.value)) not in metric_pairs:
                errors.append("report_kpi_not_in_verified_facts")
        allowed_fields = set(facts.result_columns)
        for chart in report.charts:
            if chart.x_field not in allowed_fields or chart.y_field not in allowed_fields:
                errors.append("report_chart_field_not_verified")
        expected_tables = [] if facts.empty else [
            (result.columns, result.rows)
        ]
        actual_tables = [(item.columns, item.rows) for item in report.tables]
        if actual_tables != expected_tables:
            errors.append("report_table_not_full_query_result_projection")
        return list(dict.fromkeys(errors))

    @staticmethod
    def _validate_binding(
        fact_set_id: str, fact_ids: list[str], facts: VerifiedFactSet
    ) -> list[str]:
        errors: list[str] = []
        if fact_set_id != facts.fact_set_id:
            errors.append("verified_fact_set_id_mismatch")
        if not fact_ids or len(set(fact_ids)) != len(fact_ids):
            errors.append("verified_fact_ids_missing_or_duplicate")
        if any(facts.get(item) is None for item in fact_ids):
            errors.append("verified_fact_id_unknown")
        return errors

    def _validate_text(
        self, text: str, used: list[VerifiedFact]
    ) -> list[str]:
        errors: list[str] = []
        if any(term in text for term in self._CAUSAL):
            errors.append("unverified_causal_claim")
        if any(term in text for term in self._TREND):
            errors.append("unverified_trend_claim")
        ranking_claim = bool(
            "排名" in text
            or re.search(r"第\s*\d+\s*位", text)
            or re.search(r"\btop\s*\d*\b", text, re.IGNORECASE)
        )
        if ranking_claim and not any(
            item.fact_type == FactType.RANKING for item in used
        ):
            errors.append("unverified_ranking_claim")
        if any(term in text for term in ("最高", "最大")) and not any(
            item.fact_type == FactType.MAXIMUM for item in used
        ):
            errors.append("unverified_maximum_claim")
        if any(term in text for term in ("最低", "最小")) and not any(
            item.fact_type == FactType.MINIMUM for item in used
        ):
            errors.append("unverified_minimum_claim")
        allowed_numbers = self._allowed_numbers(used)
        for token in self._NUMBER.findall(text):
            if self._normalize_number(token) not in allowed_numbers:
                errors.append("unverified_numeric_claim")
                break
        return errors

    def _allowed_numbers(self, facts: list[VerifiedFact]) -> set[str]:
        allowed: set[str] = set()
        for item in facts:
            for value in (item.value, item.values):
                self._collect_numbers(value, allowed)
            self._collect_numbers(item.dimensions, allowed)
        return allowed

    def _collect_numbers(self, value: Any, output: set[str]) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float, Decimal)):
            number = Decimal(str(value))
            output.add(self._normalize_number(str(value)))
            output.add(
                self._normalize_number(
                    format(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
                )
            )
        elif isinstance(value, (date, datetime)):
            for part in self._NUMBER.findall(value.isoformat()):
                output.add(self._normalize_number(part))
        elif isinstance(value, str):
            for part in self._NUMBER.findall(value):
                output.add(self._normalize_number(part))
        elif isinstance(value, dict):
            for item in value.values():
                self._collect_numbers(item, output)
        elif isinstance(value, list):
            for item in value:
                self._collect_numbers(item, output)

    @staticmethod
    def _normalize_number(value: str) -> str:
        try:
            normalized = value.replace(",", "")
            is_percentage = normalized.endswith("%")
            if is_percentage:
                normalized = normalized[:-1]
            number = Decimal(normalized)
            if is_percentage:
                number /= Decimal("100")
            rendered = format(number, "f")
            if "." in rendered:
                rendered = rendered.rstrip("0").rstrip(".")
            return rendered if rendered != "-0" else "0"
        except Exception:
            return value

    @staticmethod
    def _json_value(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
