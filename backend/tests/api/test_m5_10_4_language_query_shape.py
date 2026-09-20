"""Production-path M5.10.4 language and QueryShape regressions."""

from __future__ import annotations

import json

import pytest

import backend.tests.api.test_model_semantic_context as runtime_tests
from backend.app.intent.models import TurnRelation
from backend.app.intent.semantic_interpreter import (
    RankingIntent,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.intent.question_router import QuestionRouter
from backend.app.llm.base import LLMTask
from backend.app.schemas.data_contracts import QueryShape
from backend.tests.fixtures.semantic_context_domains import domains


class _OpenLanguageDraft(runtime_tests.LanguageDraft):
    """One SemanticFrame understands structure; runtime binds every ID."""

    def semantic_frame(self) -> SemanticFrame:
        dimension = (
            self.domain.month
            if self.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}
            else self.domain.dimension
        )
        evidence = next(
            phrase
            for phrase in (
                "领先的三项",
                "three leading",
                "spread across",
                "over time",
                "排一下",
            )
            if phrase in self.message
        )
        measure = next(
            item
            for item in (self.domain.measure, self.domain.measure_text)
            if item in self.message
        )
        dimension_mention = next(
            (
                item
                for item in (
                    dimension,
                    self.domain.dimension_text,
                    "monthly",
                )
                if item in self.message
            ),
            dimension,
        )
        ranking = None
        if self.shape is QueryShape.RANKING:
            ranking = RankingIntent(
                direction="desc",
                top_n=(3 if evidence in {"领先的三项", "three leading"} else None),
                evidence_span=evidence,
            )
        spans = [
            SemanticEvidenceSpan(slot="query_shape", text=evidence),
            SemanticEvidenceSpan(slot="measure", text=measure),
            SemanticEvidenceSpan(slot="dimension", text=dimension_mention),
        ]
        if ranking is not None:
            spans.append(SemanticEvidenceSpan(slot="ranking", text=evidence))
        return SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            relation=(
                TurnRelation.FOLLOW_UP
                if self.message.startswith("那么")
                else TurnRelation.FRESH_QUESTION
            ),
            query_shape=self.shape,
            measure_mentions=(measure,),
            dimension_mentions=(dimension_mention,),
            ranking_intent=ranking,
            referenced_context_slots=("query_shape",) if self.message.startswith("那么") else (),
            evidence_spans=tuple(spans),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda item: item.schema.key)
@pytest.mark.parametrize("follow_up", [False, True], ids=["current", "follow-up"])
async def test_richer_current_llm_ranking_survives_weak_router_fallback(
    monkeypatch, tmp_path, domain, follow_up
):
    prefix = "那么" if follow_up else ""
    message = f"{prefix} {domain.measure} 领先的三项 {domain.dimension}"
    router_shape = QuestionRouter().route(message).query_shape
    assert router_shape is None

    monkeypatch.setattr(runtime_tests, "LanguageDraft", _OpenLanguageDraft)
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, QueryShape.RANKING
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "completed", json.dumps(
        body.get("execution_audit"), ensure_ascii=False, indent=2
    )
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "ranking"
    assert plan["measures"] == [domain.measure]
    assert plan["dimensions"] == [domain.dimension]
    assert plan["sort"] == "desc" and plan["top_n"] == 3
    assert adapter.dax_calls == 1 and body["memory_commit"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", domains(), ids=lambda item: item.schema.key)
@pytest.mark.parametrize(
    ("shape", "message_factory", "evidence"),
    [
        (
            QueryShape.GROUPED,
            lambda domain: (
                f"{domain.measure_text} spread across {domain.dimension}"
            ),
            "spread across",
        ),
        (
            QueryShape.RANKING,
            lambda domain: (
                f"three leading {domain.dimension_text} for {domain.measure}"
            ),
            "three leading",
        ),
        (
            QueryShape.TREND,
            lambda domain: f"monthly {domain.measure} over time",
            "over time",
        ),
    ],
    ids=["mixed-grouped", "english-ranking", "english-trend"],
)
async def test_open_language_shapes_are_grounded_against_each_runtime_domain(
    monkeypatch, tmp_path, domain, shape, message_factory, evidence
):
    message = message_factory(domain)
    monkeypatch.setattr(runtime_tests, "LanguageDraft", _OpenLanguageDraft)
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, shape
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "completed", json.dumps(
        body.get("execution_audit"), ensure_ascii=False, indent=2
    )
    plan = body["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == shape.value
    assert body["execution_audit"]["query_shape_authority"] == "semantic_frame"
    assert body["execution_audit"]["semantic_frame"]["query_shape"] == shape.value
    assert adapter.dax_calls == 1 and body["memory_commit"] is True


@pytest.mark.asyncio
async def test_incomplete_open_language_ranking_clarifies_without_dax(
    monkeypatch, tmp_path
):
    domain = domains()[0]
    message = f"请把 {domain.dimension} 按照 {domain.measure} 排一下"
    assert QuestionRouter().route(message).query_shape is None

    monkeypatch.setattr(runtime_tests, "LanguageDraft", _OpenLanguageDraft)
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, QueryShape.RANKING, reject_dax=True
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "clarification_required"
    assert body["execution_audit"]["grounded_delta"]["query_shape"] == "ranking"
    assert body["execution_audit"]["clarification_reason"] == "ranking_information_incomplete"
    assert adapter.dax_calls == 0 and body["memory_commit"] is False


@pytest.mark.asyncio
async def test_unverifiable_shape_evidence_is_zero_dax_and_zero_memory(
    monkeypatch, tmp_path
):
    domain = domains()[-1]
    message = f"{domain.measure} leaderboard {domain.dimension}"

    class _InvalidEvidenceDraft(_OpenLanguageDraft):
        def semantic_frame(self):
            return SemanticFrame(
                mode=SemanticInterpretationMode.DATA,
                query_shape=QueryShape.RANKING,
                measure_mentions=(self.domain.measure,),
                dimension_mentions=(self.domain.dimension,),
                ranking_intent=RankingIntent(
                    direction="desc",
                    top_n=3,
                    evidence_span="top three",
                ),
                evidence_spans=(
                    SemanticEvidenceSpan(slot="query_shape", text="top three"),
                    SemanticEvidenceSpan(slot="measure", text=self.domain.measure),
                    SemanticEvidenceSpan(slot="dimension", text=self.domain.dimension),
                    SemanticEvidenceSpan(slot="ranking", text="top three"),
                ),
            )

    monkeypatch.setattr(runtime_tests, "LanguageDraft", _InvalidEvidenceDraft)
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, QueryShape.RANKING,
        reject_dax=True,
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "validation_failed"
    assert body["execution_audit"]["semantic_interpretation_authority"] == "semantic_frame"
    assert adapter.dax_calls == 0 and body["memory_commit"] is False
