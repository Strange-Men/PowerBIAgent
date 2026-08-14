"""Independent verifier for the restricted deterministic DAX grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.app.dax.safety import DAXSafetyValidator
from backend.app.schemas.data_contracts import (
    DAXRequest,
    FilterOperator,
    QueryPlan,
    SemanticModelSchema,
)


@dataclass(frozen=True)
class _Ref:
    table: str
    name: str


@dataclass(frozen=True)
class _ObservedFilter:
    ref: _Ref
    value: Any


@dataclass
class _ParsedDAX:
    dimensions: list[_Ref] = field(default_factory=list)
    filters: list[_ObservedFilter] = field(default_factory=list)
    time_ref: _Ref | None = None
    start_date: date | None = None
    end_date: date | None = None
    measures: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    top_n: int | None = None
    top_measure: str | None = None
    top_direction: str | None = None
    order_measure: str | None = None
    order_direction: str | None = None


class RestrictedDAXParseError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class RestrictedDAXVerifier:
    """Parse and prove plan/DAX equivalence without invoking the builder."""

    def validate(
        self,
        dax_request: DAXRequest,
        plan: QueryPlan,
        schema: SemanticModelSchema,
    ) -> list[str]:
        errors: list[str] = []
        if dax_request.semantic_model_key != plan.semantic_model_key:
            errors.append("dax_query_plan_model_mismatch")
        if plan.semantic_model_key != schema.key:
            errors.append("dax_schema_model_mismatch")
        errors.extend(DAXSafetyValidator().validate(dax_request.dax, schema).errors)
        try:
            parsed = self._parse(dax_request.dax)
        except RestrictedDAXParseError as exc:
            errors.append(exc.code)
            return list(dict.fromkeys(errors))

        measure_owners, column_owners = self._schema_owners(schema)
        expected_measures: list[str] = []
        for name in plan.measures:
            owners = measure_owners.get(name, set())
            if len(owners) != 1 or name in column_owners:
                errors.append("dax_measure_ownership_not_unique")
            expected_measures.append(name)
        if parsed.measures != expected_measures or parsed.aliases != expected_measures:
            errors.append("dax_measure_set_or_expression_mismatch")
            if any(measure not in parsed.measures for measure in expected_measures):
                errors.append("dax_missing_query_plan_measure")

        expected_dimensions: list[_Ref] = []
        for name in plan.dimensions:
            owners = column_owners.get(name, set())
            if len(owners) != 1 or name in measure_owners:
                errors.append("dax_dimension_ownership_not_unique")
            elif owners:
                expected_dimensions.append(_Ref(next(iter(owners)), name))
        if parsed.dimensions != expected_dimensions:
            if len(parsed.dimensions) > len(expected_dimensions):
                errors.append("dax_unplanned_group_by_dimension")
            else:
                errors.append("dax_missing_query_plan_dimension")

        expected_filters: list[_ObservedFilter] = []
        for item in plan.filters:
            if item.operator != FilterOperator.EQ:
                errors.append("dax_filter_operator_not_supported")
                continue
            owners = column_owners.get(item.field, set())
            if len(owners) != 1 or item.field in measure_owners:
                errors.append("dax_filter_ownership_not_unique")
                continue
            expected_filters.append(_ObservedFilter(
                _Ref(next(iter(owners)), item.field),
                self._canonical_value(
                    item.value,
                    self._column_type(
                        schema, next(iter(owners)), item.field
                    ),
                ),
            ))
        if parsed.filters != expected_filters:
            if any(item not in expected_filters for item in parsed.filters):
                errors.append("dax_filter_extra_or_changed")
            if any(item not in parsed.filters for item in expected_filters):
                errors.append("dax_filter_operator_or_value_mismatch")

        if plan.time_range is None:
            if parsed.time_ref is not None:
                errors.append("dax_unplanned_time_filter")
        else:
            owners = column_owners.get(plan.time_range.date_field, set())
            expected_ref = (
                _Ref(next(iter(owners)), plan.time_range.date_field)
                if len(owners) == 1 else None
            )
            if parsed.time_ref != expected_ref:
                errors.append("dax_time_field_mismatch")
            if parsed.start_date != plan.time_range.start_date:
                errors.append("dax_time_start_date_mismatch")
            if parsed.end_date != plan.time_range.end_date:
                errors.append("dax_time_end_date_mismatch")

        if plan.top_n is None:
            if parsed.top_n is not None:
                errors.append("dax_unplanned_top_n")
        else:
            if parsed.top_n != plan.top_n:
                errors.append("dax_top_n_value_mismatch")
            if parsed.top_measure != plan.measures[0]:
                errors.append("dax_top_n_sort_measure_mismatch")
            if parsed.top_direction != plan.sort:
                errors.append("dax_top_n_sort_direction_mismatch")

        if plan.sort is None:
            if parsed.order_measure is not None:
                errors.append("dax_unplanned_presentation_ordering")
        else:
            if parsed.order_measure is None:
                errors.append("dax_presentation_ordering_missing")
            elif parsed.order_measure != plan.measures[0]:
                errors.append("dax_presentation_sort_measure_mismatch")
            if parsed.order_measure is not None and parsed.order_direction != plan.sort:
                errors.append("dax_presentation_sort_direction_mismatch")
        return list(dict.fromkeys(errors))

    def _parse(self, dax: str) -> _ParsedDAX:
        match = re.fullmatch(
            r"\s*EVALUATE\s+(.+?)(?:\s+ORDER\s+BY\s+(.+))?\s*",
            dax,
            re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            raise RestrictedDAXParseError("dax_restricted_grammar_invalid")
        expression = match.group(1).strip()
        parsed = _ParsedDAX()
        order = match.group(2)
        if order is not None:
            order_match = re.fullmatch(
                r"\s*\[((?:\]\]|[^\]])+)\]\s+(ASC|DESC)\s*",
                order,
                re.IGNORECASE,
            )
            if order_match is None:
                raise RestrictedDAXParseError("dax_order_structure_not_verifiable")
            parsed.order_measure = self._unescape_bracket(order_match.group(1))
            parsed.order_direction = order_match.group(2).lower()

        top = self._function(expression, "TOPN")
        if top is not None:
            if top[1].strip():
                raise RestrictedDAXParseError("dax_top_n_structure_not_verifiable")
            args = self._split(top[0])
            if len(args) != 4 or not re.fullmatch(r"[1-9]\d*", args[0].strip()):
                raise RestrictedDAXParseError("dax_top_n_structure_not_verifiable")
            parsed.top_n = int(args[0].strip())
            expression = args[1].strip()
            parsed.top_measure = self._measure_ref(args[2])
            direction = args[3].strip().lower()
            if direction not in {"asc", "desc"}:
                raise RestrictedDAXParseError("dax_top_n_structure_not_verifiable")
            parsed.top_direction = direction

        summarize = self._function(expression, "SUMMARIZECOLUMNS")
        if summarize is None or summarize[1].strip():
            raise RestrictedDAXParseError("dax_restricted_grammar_invalid")
        args = self._split(summarize[0])
        index = 0
        while index < len(args):
            argument = args[index].strip()
            ref = self._qualified_ref(argument)
            if ref is not None:
                parsed.dimensions.append(ref)
                index += 1
                continue
            treatas = self._function(argument, "TREATAS")
            if treatas is not None and not treatas[1].strip():
                treatas_args = self._split(treatas[0])
                if len(treatas_args) != 2:
                    raise RestrictedDAXParseError("dax_filter_structure_not_verifiable")
                value_match = re.fullmatch(r"\s*\{(.+)\}\s*", treatas_args[0], re.DOTALL)
                filter_ref = self._qualified_ref(treatas_args[1])
                if value_match is None or filter_ref is None:
                    raise RestrictedDAXParseError("dax_filter_structure_not_verifiable")
                parsed.filters.append(_ObservedFilter(
                    filter_ref, self._parse_literal(value_match.group(1))
                ))
                index += 1
                continue
            dates = self._function(argument, "DATESBETWEEN")
            if dates is not None and not dates[1].strip():
                date_args = self._split(dates[0])
                if len(date_args) != 3 or parsed.time_ref is not None:
                    raise RestrictedDAXParseError("dax_time_structure_not_verifiable")
                parsed.time_ref = self._qualified_ref(date_args[0])
                parsed.start_date = self._parse_date(date_args[1])
                parsed.end_date = self._parse_date(date_args[2])
                if None in (parsed.time_ref, parsed.start_date, parsed.end_date):
                    raise RestrictedDAXParseError("dax_time_structure_not_verifiable")
                index += 1
                continue
            if re.match(r"FILTER\s*\(", argument, re.IGNORECASE):
                raise RestrictedDAXParseError(
                    "dax_filter_structure_not_verifiable"
                )
            break

        remaining = args[index:]
        if any(re.match(
            r"(?:FILTER|TREATAS|DATESBETWEEN)\s*\(", item, re.IGNORECASE
        ) for item in remaining):
            raise RestrictedDAXParseError(
                "dax_summarizecolumns_filter_after_name_expression"
            )
        if not remaining:
            raise RestrictedDAXParseError("dax_measure_expression_not_allowed")
        if len(remaining) % 2:
            raise RestrictedDAXParseError(
                "dax_summarizecolumns_name_expression_unpaired"
            )
        for offset in range(0, len(remaining), 2):
            parsed.aliases.append(self._parse_string(remaining[offset]))
            parsed.measures.append(self._measure_ref(remaining[offset + 1]))
        return parsed

    @classmethod
    def _function(cls, text: str, name: str) -> tuple[str, str] | None:
        match = re.match(rf"\s*{name}\s*\(", text, re.IGNORECASE)
        if match is None:
            return None
        opening = match.end() - 1
        closing = cls._matching_parenthesis(text, opening)
        if closing is None:
            raise RestrictedDAXParseError("dax_restricted_grammar_invalid")
        return text[opening + 1:closing], text[closing + 1:]

    @staticmethod
    def _matching_parenthesis(text: str, opening: int) -> int | None:
        depth = 0
        quote: str | None = None
        index = opening
        while index < len(text):
            char = text[index]
            if quote is not None:
                if char == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
            elif char in {'"', "'"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    @classmethod
    def _split(cls, text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        round_depth = brace_depth = bracket_depth = 0
        quote: str | None = None
        index = 0
        while index < len(text):
            char = text[index]
            if quote is not None:
                if char == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        index += 2
                        continue
                    quote = None
            elif char in {'"', "'"}:
                quote = char
            elif char == "(": round_depth += 1
            elif char == ")": round_depth -= 1
            elif char == "{": brace_depth += 1
            elif char == "}": brace_depth -= 1
            elif char == "[": bracket_depth += 1
            elif char == "]": bracket_depth = max(0, bracket_depth - 1)
            elif char == "," and not (round_depth or brace_depth or bracket_depth):
                parts.append(text[start:index].strip())
                start = index + 1
            index += 1
        parts.append(text[start:].strip())
        return parts

    @staticmethod
    def _qualified_ref(text: str) -> _Ref | None:
        match = re.fullmatch(
            r"\s*'((?:''|[^'])+)'\[((?:\]\]|[^\]])+)\]\s*", text
        )
        if match is None:
            return None
        return _Ref(
            table=match.group(1).replace("''", "'"),
            name=RestrictedDAXVerifier._unescape_bracket(match.group(2)),
        )

    @staticmethod
    def _unescape_bracket(value: str) -> str:
        return value.replace("]]", "]")

    @staticmethod
    def _measure_ref(text: str) -> str:
        match = re.fullmatch(r"\s*\[((?:\]\]|[^\]])+)\]\s*", text)
        if match is None:
            raise RestrictedDAXParseError("dax_measure_expression_not_allowed")
        return RestrictedDAXVerifier._unescape_bracket(match.group(1))

    @staticmethod
    def _parse_string(text: str) -> str:
        match = re.fullmatch(r'\s*"((?:""|[^"])*)"\s*', text, re.DOTALL)
        if match is None:
            raise RestrictedDAXParseError("dax_measure_alias_invalid")
        return match.group(1).replace('""', '"')

    @classmethod
    def _parse_literal(cls, text: str) -> Any:
        stripped = text.strip()
        if re.fullmatch(r'"(?:""|[^"])*"', stripped, re.DOTALL):
            return cls._parse_string(stripped)
        if stripped.upper() in {"TRUE()", "FALSE()"}:
            return stripped.upper() == "TRUE()"
        if re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
            return Decimal(stripped)
        parsed_date = cls._parse_date(stripped)
        if parsed_date is not None:
            return parsed_date
        raise RestrictedDAXParseError("dax_filter_structure_not_verifiable")

    @staticmethod
    def _parse_date(text: str) -> date | None:
        match = re.fullmatch(
            r"\s*DATE\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)\s*",
            text,
            re.IGNORECASE,
        )
        if match is None:
            return None
        try:
            return date(*(int(item) for item in match.groups()))
        except ValueError:
            return None

    @staticmethod
    def _canonical_value(value: Any, data_type: str = "") -> Any:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, int) and not isinstance(value, bool):
            return Decimal(value)
        if isinstance(value, str):
            normalized_type = data_type.casefold()
            if "date" in normalized_type or "time" in normalized_type:
                try:
                    return date.fromisoformat(value[:10])
                except ValueError:
                    return value
            return value
        return value

    @staticmethod
    def _column_type(
        schema: SemanticModelSchema, table_name: str, column_name: str
    ) -> str:
        for table in schema.tables:
            if table.name != table_name:
                continue
            for column in table.columns:
                if column.name == column_name:
                    return column.data_type
        return ""

    @staticmethod
    def _schema_owners(
        schema: SemanticModelSchema,
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        measures: dict[str, set[str]] = {}
        columns: dict[str, set[str]] = {}
        for table in schema.tables:
            if table.is_hidden or table.is_system_managed:
                continue
            for measure in table.measures:
                if not measure.is_hidden:
                    measures.setdefault(measure.name, set()).add(table.name)
            for column in table.columns:
                if not column.is_hidden:
                    columns.setdefault(column.name, set()).add(table.name)
        return measures, columns
