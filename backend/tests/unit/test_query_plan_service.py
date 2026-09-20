"""Replacement regressions for the removed natural-language QueryPlan service."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.intent.models import FilterOperator
from backend.app.intent.semantic_interpreter import (
    RankingIntent,
    SemanticEvidenceSpan,
    SemanticFilterMention,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.query_plan.semantic_frame_adapter import build_grounding_draft
from backend.app.schemas.data_contracts import QueryShape


def _frame() -> SemanticFrame:
    return SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.RANKING,
        measure_mentions=("净营收",),
        dimension_mentions=("经营分区",),
        member_mentions=("华南",),
        filter_mentions=(
            SemanticFilterMention(
                field_mention="区域",
                member_mention="华南",
                operator=FilterOperator.EQ,
                evidence_span="华南",
            ),
        ),
        ranking_intent=RankingIntent(
            direction="desc",
            top_n=3,
            evidence_span="前三",
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="前三"),
            SemanticEvidenceSpan(slot="measure", text="净营收"),
            SemanticEvidenceSpan(slot="dimension", text="经营分区"),
            SemanticEvidenceSpan(slot="member", text="华南"),
            SemanticEvidenceSpan(slot="filter", text="华南"),
            SemanticEvidenceSpan(slot="ranking", text="前三"),
        ),
    )


def test_projection_is_noncanonical_language_carrier_only() -> None:
    question = "华南经营分区净营收前三"

    draft = build_grounding_draft(
        _frame(),
        user_input=question,
        semantic_model_key="opaque-runtime-model",
    )

    assert draft.normalized_question == question
    assert draft.semantic_model_key == "opaque-runtime-model"
    assert draft.query_shape is QueryShape.RANKING
    assert draft.measures == ["净营收"]
    assert draft.dimensions == ["经营分区"]
    assert draft.filters[0].field == "区域"
    assert draft.filters[0].value == "华南"
    assert draft.sort == "desc"
    assert draft.top_n == 3
    assert not hasattr(draft, "canonical_object_ids")
    assert not hasattr(draft, "dax")


def test_projection_never_creates_an_unmentioned_member_filter() -> None:
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
        ),
    )

    draft = build_grounding_draft(
        frame,
        user_input="销售额",
        semantic_model_key="runtime-model",
    )

    assert draft.filters == []


def test_projection_deduplicates_member_already_owned_by_filter() -> None:
    draft = build_grounding_draft(
        _frame(),
        user_input="华南经营分区净营收前三",
        semantic_model_key="runtime-model",
    )

    assert [item.value for item in draft.filters] == ["华南"]


def test_projection_cannot_accept_a_ninth_query_shape() -> None:
    with pytest.raises(ValidationError):
        SemanticFrame.model_validate({
            "mode": "data",
            "query_shape": "forecast",
            "measure_mentions": ["销售额"],
        })


def test_removed_query_plan_language_authority_files_are_absent() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "query_plan"
    assert not (root / "deepseek_service.py").exists()
    assert not (root / "prompt.py").exists()
