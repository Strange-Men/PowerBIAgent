"""Deterministic restricted DAX builder for canonical M2 execution."""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnSchema,
    DAXRequest,
    FilterOperator,
    QueryShape,
    SemanticModelSchema,
)


class DAXBuildError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _SchemaOwnership:
    def __init__(self, schema: SemanticModelSchema):
        self.measure_owners: dict[str, list[tuple[str, Any]]] = {}
        self.column_owners: dict[str, list[tuple[str, ColumnSchema]]] = {}
        for table in schema.tables:
            if table.is_hidden or table.is_system_managed:
                continue
            for measure in table.measures:
                if not measure.is_hidden:
                    self.measure_owners.setdefault(measure.name, []).append(
                        (table.name, measure)
                    )
            for column in table.columns:
                if not column.is_hidden:
                    self.column_owners.setdefault(column.name, []).append(
                        (table.name, column)
                    )

    def measure(self, name: str) -> tuple[str, Any]:
        owners = self.measure_owners.get(name, [])
        if name in self.column_owners:
            raise DAXBuildError("dax_builder_measure_column_identity_conflict")
        if not owners:
            raise DAXBuildError("dax_builder_measure_not_found_or_hidden")
        if len(owners) != 1:
            raise DAXBuildError("dax_builder_measure_ownership_ambiguous")
        return owners[0]

    def column(
        self, name: str, *, table: str | None = None
    ) -> tuple[str, ColumnSchema]:
        """Resolve a column, optionally within one explicit owning table.

        ``table`` is the M3.4 deterministic ownership hint for star-schema
        duplicates (e.g. Sales[Region] vs Region[Region]).  ``None`` keeps the
        sealed M2 unique-name resolution unchanged.
        """
        owners = self.column_owners.get(name, [])
        if table is not None:
            owners = [item for item in owners if item[0] == table]
            if not owners:
                raise DAXBuildError("dax_builder_column_not_found_in_table")
            return owners[0]
        if name in self.measure_owners:
            raise DAXBuildError("dax_builder_column_measure_identity_conflict")
        if not owners:
            raise DAXBuildError("dax_builder_column_not_found_or_hidden")
        if len(owners) != 1:
            raise DAXBuildError("dax_builder_column_ownership_ambiguous")
        return owners[0]


class DeterministicDAXBuilder:
    """Compile only the explicitly supported CanonicalQueryPlan grammar."""

    def build(
        self,
        plan: CanonicalQueryPlan,
        schema: SemanticModelSchema,
        *,
        request_id: str = "",
        max_rows: int = 1000,
        timeout_seconds: int = 30,
    ) -> DAXRequest:
        if plan.semantic_model_key != schema.key:
            raise DAXBuildError("dax_builder_model_mismatch")
        if plan.comparison_mode is not None:
            raise DAXBuildError("dax_builder_comparison_unsupported")
        if not plan.measures and plan.query_shape != QueryShape.ENTITY_LIST:
            raise DAXBuildError("dax_builder_measure_required")
        if plan.query_shape == QueryShape.ENTITY_LIST and not plan.dimensions:
            raise DAXBuildError("dax_builder_entity_list_dimension_required")
        if len(set(plan.measures)) != len(plan.measures):
            raise DAXBuildError("dax_builder_duplicate_measure")
        if len(set(plan.dimensions)) != len(plan.dimensions):
            raise DAXBuildError("dax_builder_duplicate_dimension")
        if plan.top_n is not None and plan.sort is None:
            raise DAXBuildError("dax_builder_top_n_sort_required")
        if plan.top_n is not None and not plan.dimensions:
            raise DAXBuildError("dax_builder_top_n_dimension_required")
        if plan.sort is not None and len(plan.measures) != 1:
            raise DAXBuildError("dax_builder_sort_single_measure_required")

        ownership = _SchemaOwnership(schema)
        measures = [
            (name, ownership.measure(name)[0]) for name in plan.measures
        ]
        dimension_hints = plan.dimension_tables or {}
        dimensions = [
            (
                name,
                *ownership.column(name, table=dimension_hints.get(name)),
            )
            for name in plan.dimensions
        ]

        arguments: list[str] = [
            self._qualified(table, name) for name, table, _ in dimensions
        ]
        for item in plan.filters:
            if item.operator not in {FilterOperator.EQ, FilterOperator.IN_SET}:
                raise DAXBuildError("dax_builder_filter_operator_unsupported")
            table, column = ownership.column(
                item.field, table=dimension_hints.get(item.field)
            )
            values = (
                item.value
                if item.operator == FilterOperator.IN_SET
                and isinstance(item.value, (list, tuple))
                else [item.value]
            )
            if item.operator == FilterOperator.IN_SET and not values:
                raise DAXBuildError("dax_builder_in_set_values_required")
            literal = ", ".join(
                self._literal(value, column.data_type) for value in values
            )
            arguments.append(
                f"TREATAS({{{literal}}}, {self._qualified(table, item.field)})"
            )

        if plan.time_range is not None:
            time = plan.time_range
            table, column = ownership.column(
                time.date_field, table=dimension_hints.get(time.date_field)
            )
            if not self._is_date_type(column.data_type):
                raise DAXBuildError("dax_builder_time_field_type_invalid")
            arguments.append(
                "DATESBETWEEN("
                f"{self._qualified(table, time.date_field)}, "
                f"{self._date_literal(time.start_date)}, "
                f"{self._date_literal(time.end_date)})"
            )

        for measure, _ in measures:
            arguments.extend((self._string_literal(measure), self._measure(measure)))

        table_expression = "SUMMARIZECOLUMNS(\n    " + ",\n    ".join(arguments) + "\n)"
        if plan.top_n is not None:
            direction = plan.sort.upper()
            tie_breakers = "".join(
                f",\n    {self._qualified(table, name)},\n    ASC"
                for name, table, _ in dimensions
            )
            table_expression = (
                f"TOPN(\n    {plan.top_n},\n    {table_expression},\n"
                f"    {self._measure(plan.measures[0])},\n    {direction}"
                f"{tie_breakers}\n)"
            )

        dax = f"EVALUATE\n{table_expression}"
        if plan.sort is not None:
            order_items = [
                f"{self._measure(plan.measures[0])} {plan.sort.upper()}",
                *(f"{self._qualified(table, name)} ASC" for name, table, _ in dimensions),
            ]
            dax += "\nORDER BY " + ", ".join(order_items)
        elif plan.dimension_order is not None:
            if not dimensions:
                raise DAXBuildError("dax_builder_dimension_order_dimension_required")
            dax += "\nORDER BY " + ", ".join(
                f"{self._qualified(table, name)} {plan.dimension_order.upper()}"
                for name, table, _ in dimensions
            )
        return DAXRequest(
            semantic_model_key=plan.semantic_model_key,
            dax=dax,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
            request_id=request_id,
            is_mock=False,
        )

    @staticmethod
    def _qualified(table: str, field: str) -> str:
        return f"'{table.replace(chr(39), chr(39) * 2)}'[{field.replace(']', ']]')}]"

    @staticmethod
    def _measure(name: str) -> str:
        return f"[{name.replace(']', ']]')}]"

    @staticmethod
    def _string_literal(value: str) -> str:
        return f'"{value.replace(chr(34), chr(34) * 2)}"'

    @classmethod
    def _literal(cls, value: Any, data_type: str) -> str:
        if value is None:
            raise DAXBuildError("dax_builder_null_filter_unsupported")
        if isinstance(value, bool):
            return "TRUE()" if value else "FALSE()"
        if isinstance(value, datetime):
            return cls._date_literal(value.date())
        if isinstance(value, date):
            return cls._date_literal(value)
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            if isinstance(value, float) and not math.isfinite(value):
                raise DAXBuildError("dax_builder_numeric_literal_invalid")
            try:
                decimal = Decimal(str(value))
            except InvalidOperation as exc:
                raise DAXBuildError("dax_builder_numeric_literal_invalid") from exc
            rendered = format(decimal, "f")
            if "." in rendered:
                rendered = rendered.rstrip("0").rstrip(".")
            return rendered if rendered and rendered != "-0" else "0"
        if isinstance(value, str):
            if cls._is_date_type(data_type):
                try:
                    return cls._date_literal(date.fromisoformat(value[:10]))
                except ValueError as exc:
                    raise DAXBuildError("dax_builder_date_literal_invalid") from exc
            return cls._string_literal(value)
        raise DAXBuildError("dax_builder_literal_type_unsupported")

    @staticmethod
    def _date_literal(value: date) -> str:
        return f"DATE({value.year},{value.month},{value.day})"

    @staticmethod
    def _is_date_type(data_type: str) -> bool:
        normalized = data_type.casefold()
        return "date" in normalized or "time" in normalized
