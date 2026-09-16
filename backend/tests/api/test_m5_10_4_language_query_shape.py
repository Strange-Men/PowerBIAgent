"""Production-path M5.10.4 language and QueryShape regressions."""

from __future__ import annotations

import json

import pytest

import backend.tests.api.test_model_semantic_context as runtime_tests
from backend.app.intent.models import IntentSpec, IntentType, TurnRelation
from backend.app.intent.question_router import QuestionRouter
from backend.app.llm.base import LLMResponse, LLMTask
from backend.app.schemas.data_contracts import QueryPlan, QueryShape
from backend.tests.fixtures.semantic_context_domains import domains


class _OpenLanguageDraft(runtime_tests.LanguageDraft):
    """Existing QueryPlan call interprets structure; it owns no runtime ID."""

    async def generate(self, request, output_type):
        dimension = (
            self.domain.month
            if self.shape in {QueryShape.TREND, QueryShape.BOUNDED_TREND}
            else self.domain.dimension
        )
        if request.task == LLMTask.INTENT_RECOGNITION:
            output = IntentSpec(
                intent=IntentType.DATA_QUESTION,
                confidence=1,
                normalized_question=self.message,
                turn_relation=(
                    TurnRelation.FOLLOW_UP
                    if self.message.startswith("那么")
                    else TurnRelation.FRESH_QUESTION
                ),
                detected_measures=[self.domain.measure],
                detected_dimensions=[dimension],
            )
        elif request.task == LLMTask.QUERY_PLAN:
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
            output = QueryPlan(
                normalized_question=self.message,
                semantic_model_key=self.domain.schema.key,
                query_shape=self.shape,
                query_shape_evidence=evidence,
                measures=[self.domain.measure],
                dimensions=[dimension],
                # Deliberately hallucinate complete ranking slots for the open
                # form: Grounding must reject the unevidenced bound.
                sort="desc" if self.shape == QueryShape.RANKING else None,
                top_n=3 if self.shape == QueryShape.RANKING else None,
            )
        else:
            return await super().generate(request, output_type)
        return LLMResponse(
            content="{}", structured=output, model="offline-open-language"
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
    assert router_shape is (None if follow_up else QueryShape.SCALAR)

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
    audit = body["execution_audit"]["query_shape_reconciliation"]
    assert audit["draft_evidence"] == evidence
    if audit["router_strength"] != "high_confidence":
        assert audit["source"] == "current_llm_draft"
    assert adapter.dax_calls == 1 and body["memory_commit"] is True


@pytest.mark.asyncio
async def test_incomplete_open_language_ranking_clarifies_without_dax(
    monkeypatch, tmp_path
):
    domain = domains()[0]
    message = f"请把 {domain.dimension} 按照 {domain.measure} 排一下"
    assert QuestionRouter().route(message).query_shape == QueryShape.SCALAR

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
        async def generate(self, request, output_type):
            if request.task != LLMTask.QUERY_PLAN:
                return await super().generate(request, output_type)
            output = QueryPlan(
                normalized_question=self.message,
                semantic_model_key=self.domain.schema.key,
                query_shape=QueryShape.RANKING,
                query_shape_evidence="top three",
                measures=[self.domain.measure],
                dimensions=[self.domain.dimension],
                sort="desc",
                top_n=3,
            )
            return LLMResponse(
                content="{}", structured=output, model="offline-open-language"
            )

    monkeypatch.setattr(runtime_tests, "LanguageDraft", _InvalidEvidenceDraft)
    app, adapter, database = runtime_tests.create_runtime_app(
        monkeypatch, tmp_path, domain, message, QueryShape.RANKING,
        reject_dax=True,
    )
    body = await runtime_tests.owned_request(
        app, database, tmp_path, domain, message
    )

    assert body["terminal_state"] == "clarification_required"
    audit = body["execution_audit"]["query_shape_reconciliation"]
    assert audit["effective"] == "ranking"
    assert audit["draft_evidence"] is None
    assert audit["requires_clarification"] is True
    assert adapter.dax_calls == 0 and body["memory_commit"] is False
