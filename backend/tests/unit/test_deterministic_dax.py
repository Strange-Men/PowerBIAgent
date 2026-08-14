"""Restricted deterministic DAX builder and independent Layer 3."""

from datetime import date

import pytest

from backend.app.dax.builder import DAXBuildError, DeterministicDAXBuilder
from backend.app.harness.validators.validation_service import ValidationService
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnSchema,
    FilterOperator,
    MeasureSchema,
    SemanticModelSchema,
    StructuredFilter,
    TableSchema,
    TimeRangeMode,
    TimeRangeSpec,
)


def _schema(*, ambiguous: bool = False) -> SemanticModelSchema:
    tables = [TableSchema(
        name="Sales",
        columns=[
            ColumnSchema(name="Category", data_type="string"),
            ColumnSchema(name="Product", data_type="string"),
            ColumnSchema(name="OrderDate", data_type="datetime"),
            ColumnSchema(name="Quantity", data_type="int64"),
            ColumnSchema(name="Active", data_type="boolean"),
        ],
        measures=[
            MeasureSchema(name="Total Sales", expression="SUM('Sales'[Quantity])"),
            MeasureSchema(name="Total Quantity", expression="SUM('Sales'[Quantity])"),
        ],
    )]
    if ambiguous:
        tables.append(TableSchema(
            name="Other",
            columns=[ColumnSchema(name="Category", data_type="string")],
            measures=[MeasureSchema(name="Total Sales", expression="1")],
        ))
    return SemanticModelSchema(name="Test", key="model", tables=tables)


def _plan(**updates) -> CanonicalQueryPlan:
    values = {
        "normalized_question": "query",
        "semantic_model_key": "model",
        "measures": ["Total Sales"],
    }
    values.update(updates)
    return CanonicalQueryPlan(**values)


def _build(plan=None, schema=None):
    return DeterministicDAXBuilder().build(plan or _plan(), schema or _schema())


def _layer3(request, plan, schema=None):
    return ValidationService(allowed_semantic_models=["model"]).validate_dax_query_plan_consistency(
        request, plan, schema or _schema()
    )


@pytest.mark.parametrize("plan", [
    _plan(),
    _plan(dimensions=["Category"]),
    _plan(filters=[StructuredFilter(field="Category", value="Furniture")]),
    _plan(
        dimensions=["Product"],
        filters=[StructuredFilter(field="Category", value="Furniture")],
    ),
    _plan(time_range=TimeRangeSpec(
        date_field="OrderDate",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 8, 14),
        mode=TimeRangeMode.EXPLICIT_RANGE,
    )),
    _plan(dimensions=["Product"], sort="desc", top_n=3),
])
def test_supported_shapes_build_and_independent_layer3_pass(plan):
    request = _build(plan)
    assert _layer3(request, plan).is_valid
    assert request.dax == _build(plan).dax


def test_filter_without_dimension_never_becomes_group_by():
    plan = _plan(filters=[StructuredFilter(field="Category", value="Furniture")])
    request = _build(plan)
    assert "TREATAS({\"Furniture\"}, 'Sales'[Category])" in request.dax
    assert request.dax.index("TREATAS") < request.dax.index('"Total Sales"')
    assert _layer3(request, plan).is_valid


@pytest.mark.parametrize("field,value,expected", [
    ("Category", 'A"B', '"A""B"'),
    ("Quantity", 100, "100"),
    ("Active", True, "TRUE()"),
    ("OrderDate", "2026-08-14", "DATE(2026,8,14)"),
])
def test_eq_literal_serialization(field, value, expected):
    plan = _plan(filters=[StructuredFilter(field=field, value=value)])
    request = _build(plan)
    assert expected in request.dax
    assert _layer3(request, plan).is_valid


@pytest.mark.parametrize("plan,code", [
    (_plan(measures=["Missing"]), "dax_builder_measure_not_found_or_hidden"),
    (_plan(dimensions=["Missing"]), "dax_builder_column_not_found_or_hidden"),
    (_plan(filters=[StructuredFilter(
        field="Category", operator=FilterOperator.GT, value="A"
    )]), "dax_builder_filter_operator_unsupported"),
])
def test_builder_rejects_wrong_objects_and_unsupported_operator(plan, code):
    with pytest.raises(DAXBuildError, match=code):
        _build(plan)


def test_builder_rejects_ambiguous_ownership():
    with pytest.raises(DAXBuildError, match="ownership_ambiguous"):
        _build(_plan(), _schema(ambiguous=True))


def test_layer3_rejects_extra_and_missing_group_by():
    plan = _plan(dimensions=["Product"])
    built = _build(plan)
    extra = built.model_copy(update={
        "dax": built.dax.replace(
            "'Sales'[Product],", "'Sales'[Product],\n    'Sales'[Category],"
        )
    })
    missing = built.model_copy(update={
        "dax": built.dax.replace("    'Sales'[Product],\n", "")
    })
    assert "dax_unplanned_group_by_dimension" in _layer3(extra, plan).errors
    assert "dax_missing_query_plan_dimension" in _layer3(missing, plan).errors


def test_layer3_rejects_changed_and_extra_filter():
    plan = _plan(filters=[StructuredFilter(field="Category", value="Furniture")])
    built = _build(plan)
    changed = built.model_copy(update={
        "dax": built.dax.replace('"Furniture"', '"Electronics"')
    })
    extra_plan = _plan()
    extra_built = _build(extra_plan)
    extra = extra_built.model_copy(update={
        "dax": extra_built.dax.replace(
            '    "Total Sales"',
            '    TREATAS({"Furniture"}, \'Sales\'[Category]),\n    "Total Sales"',
        )
    })
    assert "dax_filter_operator_or_value_mismatch" in _layer3(changed, plan).errors
    assert "dax_filter_extra_or_changed" in _layer3(extra, extra_plan).errors


def test_layer3_rejects_changed_time_field_and_boundary():
    plan = _plan(time_range=TimeRangeSpec(
        date_field="OrderDate",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 8, 14),
        mode=TimeRangeMode.EXPLICIT_RANGE,
    ))
    built = _build(plan)
    field = built.model_copy(update={
        "dax": built.dax.replace("'Sales'[OrderDate]", "'Sales'[Product]")
    })
    boundary = built.model_copy(update={
        "dax": built.dax.replace("DATE(2026,1,1)", "DATE(2026,1,2)")
    })
    assert "dax_time_field_mismatch" in _layer3(field, plan).errors
    assert "dax_time_start_date_mismatch" in _layer3(boundary, plan).errors


def test_layer3_rejects_wrong_topn_and_raw_reaggregation():
    top_plan = _plan(dimensions=["Product"], sort="desc", top_n=3)
    top = _build(top_plan)
    wrong_top = top.model_copy(update={"dax": top.dax.replace("    3,", "    4,")})
    scalar_plan = _plan()
    scalar = _build(scalar_plan)
    raw = scalar.model_copy(update={
        "dax": scalar.dax.replace(
            '[Total Sales]\n)', "SUM('Sales'[Quantity])\n)"
        )
    })
    assert "dax_top_n_value_mismatch" in _layer3(wrong_top, top_plan).errors
    assert "dax_measure_expression_not_allowed" in _layer3(raw, scalar_plan).errors
