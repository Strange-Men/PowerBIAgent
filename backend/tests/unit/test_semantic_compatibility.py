"""Permanent semantic compatibility and metamorphic regression firewall."""

from __future__ import annotations

import random
from datetime import date

import pytest

from backend.app.intent.models import IntentSpec, IntentType
from backend.app.intent.unsupported_policy import (
    CapabilityClass,
    classify_capability,
    deterministic_unsupported_reason,
)
from backend.app.query_plan.grounding import (
    GroundingStatus,
    SemanticGroundingService,
)
from backend.app.query_plan.semantic_catalog import (
    GlossaryCatalogError,
    SemanticCatalogBuilder,
    compute_schema_fingerprint,
)
from backend.app.schemas.data_contracts import (
    ColumnMembersResult,
    ColumnSchema,
    MeasureSchema,
    QueryPlan,
    SemanticModelSchema,
    TableSchema,
)


def _sales_schema(*, include_ship_date: bool = False) -> SemanticModelSchema:
    columns = [
        ColumnSchema(name="Region", data_type="String"),
        ColumnSchema(name="Product", data_type="String"),
        ColumnSchema(name="OrderDate", data_type="DateTime"),
    ]
    if include_ship_date:
        columns.append(ColumnSchema(name="ShipDate", data_type="DateTime"))
    return SemanticModelSchema(
        name="Semantic Compatibility Sales",
        key="semantic_compat_sales",
        tables=[TableSchema(
            name="SalesFacts",
            columns=columns,
            measures=[MeasureSchema(name="NetRevenue", data_type="Double")],
        )],
    )


def _sales_glossary(
    schema: SemanticModelSchema,
    *,
    default_date: str | None = "OrderDate",
) -> dict[str, object]:
    fields: dict[str, object] = {
        "Region": {
            "table_name": "SalesFacts",
            "object_type": "field",
            "aliases": ["区域", "地区"],
            "member_aliases": {"华南": "South", "华南区": "South"},
            "member_suffixes": ["区"],
        },
        "Product": {
            "table_name": "SalesFacts",
            "object_type": "field",
            "aliases": ["产品", "商品"],
        },
        "OrderDate": {
            "table_name": "SalesFacts",
            "object_type": "field",
            "aliases": ["订单日期", "销售日期"],
        },
    }
    if default_date == "OrderDate":
        fields["OrderDate"]["temporal_role"] = "default"  # type: ignore[index]
    if any(column.name == "ShipDate" for column in schema.tables[0].columns):
        fields["ShipDate"] = {
            "table_name": "SalesFacts",
            "object_type": "field",
            "aliases": ["发货日期"],
            **({"temporal_role": "default"} if default_date == "ShipDate" else {}),
        }
    return {
        "version": 1,
        "semantic_model_key": schema.key,
        "schema_fingerprint": compute_schema_fingerprint(schema),
        "measures": {
            "NetRevenue": {
                "table_name": "SalesFacts",
                "object_type": "measure",
                "aliases": ["销售额", "总销售额", "销售金额"],
            }
        },
        "fields": fields,
    }


def _catalog(*, include_ship_date: bool = False, default_date: str | None = "OrderDate"):
    schema = _sales_schema(include_ship_date=include_ship_date)
    return SemanticCatalogBuilder().build_from_data(
        schema,
        _sales_glossary(schema, default_date=default_date),
    )


def _intent(question: str) -> IntentSpec:
    return IntentSpec(
        intent=IntentType.DATA_QUESTION,
        confidence=0.9,
        normalized_question=question,
    )


def _draft(question: str, model_key: str = "semantic_compat_sales") -> QueryPlan:
    return QueryPlan(
        normalized_question=question,
        semantic_model_key=model_key,
    )


async def _members(field, limit):
    assert limit == 100
    values = ["South", "East"] if field.canonical_name == "Region" else []
    return ColumnMembersResult(
        semantic_model_key="semantic_compat_sales",
        table_name=field.table_name,
        field_name=field.canonical_name,
        values=values,
        source_mode="real",
    )


@pytest.mark.asyncio
async def test_seeded_wording_metamorphs_preserve_canonical_slots():
    """Equivalent wording/order/spacing/punctuation must keep one meaning."""

    rng = random.Random(571)
    measures = ["销售额", "总销售额", "销售金额"]
    times = ["2025年5月", "2025年5月份", "2025-05", "２０２５年５月"]
    templates = [
        "{time}{measure}",
        "{measure}，{time}",
        " {measure} / {time} ",
        "{time} 的 {measure} 是多少？",
    ]
    generated = [
        rng.choice(templates).format(
            measure=rng.choice(measures),
            time=rng.choice(times),
        )
        for _ in range(64)
    ]

    for question in generated:
        outcome = await SemanticGroundingService(
            _catalog(), today=lambda: date(2026, 8, 13)
        ).ground(question, _intent(question), _draft(question), None, _members)
        assert outcome.status == GroundingStatus.RESOLVED, question
        assert outcome.delta is not None
        assert outcome.delta.measures == ["NetRevenue"], question
        assert outcome.delta.time_range is not None
        assert outcome.delta.time_range.date_field == "OrderDate", question
        assert outcome.delta.time_range.start_date == date(2025, 5, 1), question
        assert outcome.delta.time_range.end_date == date(2025, 5, 31), question


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "华南区2025年5月销售额",
        "2025年5月华南销售金额",
        "总销售额，华南，2025-05",
        "２０２５年５月份 ／ 华南区 ／ 销售额",
    ],
)
async def test_word_order_and_nfkc_preserve_runtime_member_truth(question):
    outcome = await SemanticGroundingService(
        _catalog(), today=lambda: date(2026, 8, 13)
    ).ground(question, _intent(question), _draft(question), None, _members)

    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.measures == ["NetRevenue"]
    assert outcome.delta.filters is not None
    assert outcome.delta.filters[0].field == "Region"
    assert outcome.delta.filters[0].value == "South"
    assert outcome.delta.time_range is not None
    assert outcome.delta.time_range.start_date == date(2025, 5, 1)


@pytest.mark.asyncio
async def test_unknown_member_and_unproven_date_role_remain_unresolved():
    unknown_member = await SemanticGroundingService(_catalog()).ground(
        "火星区销售额",
        _intent("火星区销售额"),
        _draft("火星区销售额"),
        None,
        _members,
    )
    assert unknown_member.status == GroundingStatus.UNRESOLVED
    assert unknown_member.delta is None

    ambiguous_role = await SemanticGroundingService(
        _catalog(include_ship_date=True, default_date=None)
    ).ground(
        "2025年5月销售额",
        _intent("2025年5月销售额"),
        _draft("2025年5月销售额"),
        None,
        _members,
    )
    assert ambiguous_role.status == GroundingStatus.AMBIGUOUS
    assert ambiguous_role.delta is None


@pytest.mark.asyncio
async def test_explicit_date_role_beats_model_scoped_default():
    question = "按发货日期看2025年5月销售额"
    outcome = await SemanticGroundingService(
        _catalog(include_ship_date=True), today=lambda: date(2026, 8, 13)
    ).ground(question, _intent(question), _draft(question), None, _members)

    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.time_range is not None
    assert outcome.delta.time_range.date_field == "ShipDate"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("大概销售额是多少", CapabilityClass.READ_ANALYSIS),
        ("估算明年销售额", CapabilityClass.FUTURE_PREDICTION),
        ("预测明年销售额", CapabilityClass.FUTURE_PREDICTION),
        ("删除所有数据", CapabilityClass.DATA_DELETE),
        ("写入 Power BI 模型", CapabilityClass.MODEL_WRITE),
    ],
)
def test_capability_boundary_is_wording_stable(message, expected):
    assert classify_capability(message) == expected
    if expected == CapabilityClass.READ_ANALYSIS:
        assert deterministic_unsupported_reason(message) is None
    else:
        assert deterministic_unsupported_reason(message) is not None


@pytest.mark.parametrize("mutation", ["rename", "remove", "type_change"])
def test_schema_mutation_invalidates_model_scoped_temporal_authority(mutation):
    schema = _sales_schema()
    glossary = _sales_glossary(schema)
    mutated = schema.model_copy(deep=True)
    if mutation == "rename":
        mutated.tables[0].columns[-1].name = "BookedAt"
    elif mutation == "remove":
        mutated.tables[0].columns.pop()
    else:
        mutated.tables[0].columns[-1].data_type = "String"

    with pytest.raises(GlossaryCatalogError):
        SemanticCatalogBuilder().build_from_data(mutated, glossary)


def test_additive_schema_mutation_does_not_change_canonical_identity():
    schema = _sales_schema()
    glossary = _sales_glossary(schema)
    mutated = schema.model_copy(deep=True)
    mutated.tables[0].columns.append(
        ColumnSchema(name="UnrelatedNote", data_type="String")
    )

    catalog = SemanticCatalogBuilder().build_from_data(mutated, glossary)
    revenue = next(obj for obj in catalog.objects if obj.canonical_name == "NetRevenue")
    assert revenue.table_name == "SalesFacts"
    assert catalog.schema_drift is True
