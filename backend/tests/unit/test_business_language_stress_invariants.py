"""Cross-domain invariants for SemanticFrame -> runtime grounding."""

import pytest

from backend.app.intent.semantic_interpreter import (
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.query_plan.grounding import GroundingStatus, SemanticGroundingService
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)
from backend.app.schemas.data_contracts import ColumnMembersResult, QueryShape


DOMAINS = (
    ("retail", "销售额", "Total Sales", "产品", "Product"),
    ("education", "平均成绩", "Average Score", "学校", "School"),
    ("inventory", "库存余额", "Stock Balance", "仓库", "Warehouse"),
    ("logistics", "运单数", "Shipment Count", "承运商", "Carrier"),
    ("unknown-holdout", "指标甲", "Metric X", "实体乙", "Entity X"),
)


def _catalog(key: str, measure_text: str, measure: str, dimension_text: str, dimension: str) -> SemanticCatalog:
    return SemanticCatalog(
        semantic_model_key=key,
        schema_fingerprint="1" * 64,
        objects=(
            CatalogObject(
                object_id=f"measure:Facts:{measure}",
                canonical_name=measure,
                object_type=SemanticObjectType.MEASURE,
                table_name="Facts",
                data_type="decimal",
                aliases=(measure_text,),
            ),
            CatalogObject(
                object_id=f"field:Facts:{dimension}",
                canonical_name=dimension,
                object_type=SemanticObjectType.FIELD,
                table_name="Facts",
                data_type="string",
                aliases=(dimension_text,),
            ),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "measure_text", "measure", "dimension_text", "dimension"),
    DOMAINS,
)
async def test_cross_domain_grouping_binds_only_runtime_objects(
    key: str,
    measure_text: str,
    measure: str,
    dimension_text: str,
    dimension: str,
) -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.GROUPED,
        measure_mentions=(measure_text,),
        dimension_mentions=(dimension_text,),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="按"),
            SemanticEvidenceSpan(slot="measure", text=measure_text),
            SemanticEvidenceSpan(slot="dimension", text=dimension_text),
        ),
    )

    async def unused_lookup(field, limit):
        return ColumnMembersResult(
            semantic_model_key=key,
            table_name=field.table_name,
            field_name=field.canonical_name,
            values=[],
            source_mode="real",
        )

    outcome = await SemanticGroundingService(
        _catalog(key, measure_text, measure, dimension_text, dimension)
    ).ground_frame(
        f"按{dimension_text}看{measure_text}",
        frame,
        None,
        unused_lookup,
    )

    assert outcome.status is GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.measures == [measure]
    assert outcome.delta.dimensions == [dimension]


@pytest.mark.parametrize(
    ("key", "measure_text", "measure", "dimension_text", "dimension"),
    DOMAINS,
)
def test_catalog_domain_words_live_only_in_test_runtime_metadata(
    key: str,
    measure_text: str,
    measure: str,
    dimension_text: str,
    dimension: str,
) -> None:
    catalog = _catalog(key, measure_text, measure, dimension_text, dimension)
    assert {item.canonical_name for item in catalog.objects} == {measure, dimension}
    assert all(item.source.value == "runtime" for item in catalog.objects)


def test_general_location_recommendation_has_zero_business_slots() -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.GENERAL,
        general_answer="我没有实时地点工具，但可以按预算和偏好帮你整理选择标准。",
    )
    assert frame.query_shape is None
    assert frame.measure_mentions == ()
    assert frame.member_mentions == ()
