"""M5.9.3 deterministic model/shape/factor/wording regression matrix."""

from __future__ import annotations

import pytest

from backend.app.intent.semantic_interpreter import (
    RankingIntent,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.intent.question_router import QuestionRoute, QuestionRouter
from backend.app.intent.temporal_expression import parse_explicit_month_range
from backend.app.query_plan.grounding import GroundingStatus, SemanticGroundingService
from backend.app.query_plan.semantic_catalog import (
    SemanticCatalogBuilder,
    compute_schema_fingerprint,
)
from backend.app.schemas.data_contracts import (
    ColumnSchema,
    MeasureSchema,
    QueryShape,
    SemanticModelSchema,
    TableSchema,
)


MODEL_TERMS = (
    ("sales", "Region", "区域", "Revenue", "销售额"),
    ("education", "Course", "课程", "Average Score", "平均分"),
    ("inventory", "Warehouse", "仓库", "Stock Quantity", "库存量"),
    ("logistics", "Carrier", "承运商", "Shipment Count", "运单数"),
)

GROUPING_WORDINGS = (
    "各{dimension}{measure}",
    "每个{dimension}{measure}",
    "按{dimension}统计{measure}",
    "{dimension}{measure}分别是多少",
    "2025年各{dimension}{measure}分别是多少？",
)

MONTH_RANGE_WORDINGS = (
    "2025年1月至6月每个月的{measure}趋势",
    "2025年1月到6月按月看{measure}",
    "2025年1月-6月{measure}月度趋势",
    "2025年1月至2025年6月每月{measure}趋势",
    "2025-01~2025-06每个月的{measure}趋势",
    "2025-01 至 2025-06按月看{measure}",
    "２０２５年１月至６月每个月的{measure}趋势",
)

RANKING_WORDINGS = (
    "前3个{dimension}呢？",
    "前三个{dimension}呢？",
    "前十个{dimension}{measure}",
    "{measure}最高的前三个{dimension}是什么？",
)


@pytest.mark.parametrize(
    ("model", "question"),
    [
        (model, wording.format(dimension=dimension, measure=measure))
        for model, _, dimension, _, measure in MODEL_TERMS
        for wording in GROUPING_WORDINGS
    ],
)
def test_grouping_matrix_is_not_member_set(model: str, question: str) -> None:
    decision = QuestionRouter().route(question)

    assert model
    assert decision.route == QuestionRoute.LLM_SEMANTIC_INTERPRETATION
    assert decision.query_shape is None


@pytest.mark.parametrize(
    ("model", "question"),
    [
        (model, wording.format(measure=measure))
        for model, _, _, _, measure in MODEL_TERMS
        for wording in MONTH_RANGE_WORDINGS
    ],
)
def test_explicit_month_range_matrix_preserves_both_endpoints(
    model: str, question: str
) -> None:
    decision = QuestionRouter().route(question)
    parsed = parse_explicit_month_range(question)

    assert model
    assert decision.route == QuestionRoute.LLM_SEMANTIC_INTERPRETATION
    assert decision.query_shape is None
    assert parsed is not None
    assert (parsed.start_year, parsed.start_month) == (2025, 1)
    assert (parsed.end_year, parsed.end_month) == (2025, 6)


@pytest.mark.parametrize(
    ("model", "question"),
    [
        (model, wording.format(dimension=dimension, measure=measure))
        for model, _, dimension, _, measure in MODEL_TERMS
        for wording in RANKING_WORDINGS
    ],
)
def test_ranking_matrix_preserves_chinese_and_numeric_top_n_shape(
    model: str, question: str
) -> None:
    decision = QuestionRouter().route(question)

    assert model
    assert decision.route == QuestionRoute.LLM_SEMANTIC_INTERPRETATION
    assert decision.query_shape is None
    top_n = 10 if "十" in question else 3
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.RANKING,
        measure_mentions=((next((item[4] for item in MODEL_TERMS if item[0] == model), "指标")),),
        dimension_mentions=((next((item[2] for item in MODEL_TERMS if item[0] == model), "维度")),),
        ranking_intent=RankingIntent(
            direction="desc", top_n=top_n, evidence_span=question
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text=question),
            SemanticEvidenceSpan(slot="measure", text=(next((item[4] for item in MODEL_TERMS if item[0] == model), "指标"))),
            SemanticEvidenceSpan(slot="dimension", text=(next((item[2] for item in MODEL_TERMS if item[0] == model), "维度"))),
            SemanticEvidenceSpan(slot="ranking", text=question),
        ),
    )
    assert frame.ranking_intent.top_n == top_n


def _catalog(
    model: str,
    field: str,
    dimension: str,
    measure_name: str,
    measure: str,
):
    schema = SemanticModelSchema(
        name=model,
        key=f"{model}_model",
        tables=[TableSchema(
            name="Facts",
            columns=[ColumnSchema(name=field, data_type="String")],
            measures=[MeasureSchema(name=measure_name, data_type="Double")],
        )],
    )
    glossary = {
        "version": 1,
        "semantic_model_key": schema.key,
        "schema_fingerprint": compute_schema_fingerprint(schema),
        "measures": {
            measure_name: {
                "table_name": "Facts",
                "object_type": "measure",
                "aliases": [measure],
            },
        },
        "fields": {
            field: {
                "table_name": "Facts",
                "object_type": "field",
                "aliases": [dimension],
            },
        },
    }
    return SemanticCatalogBuilder().build_from_data(schema, glossary)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "field", "dimension", "measure_name", "measure", "wording"),
    [
        (*terms, wording)
        for terms in MODEL_TERMS
        for wording in GROUPING_WORDINGS[:-1]
    ],
)
async def test_grouping_filter_firewall_matrix(
    model: str,
    field: str,
    dimension: str,
    measure_name: str,
    measure: str,
    wording: str,
) -> None:
    question = wording.format(dimension=dimension, measure=measure)

    async def no_lookup(*_):
        raise AssertionError("GROUPED wording must not invoke member lookup")

    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.GROUPED,
        measure_mentions=(measure,),
        dimension_mentions=(dimension,),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text=question),
            SemanticEvidenceSpan(slot="measure", text=measure),
            SemanticEvidenceSpan(slot="dimension", text=dimension),
        ),
    )
    outcome = await SemanticGroundingService(
        _catalog(model, field, dimension, measure_name, measure)
    ).ground_frame(question, frame, None, no_lookup)

    assert outcome.status == GroundingStatus.RESOLVED
    assert outcome.delta is not None
    assert outcome.delta.query_shape == QueryShape.GROUPED
    assert outcome.delta.dimensions == [field]
    assert outcome.delta.filters is None
