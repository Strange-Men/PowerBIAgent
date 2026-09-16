"""M5.10.3 production-path regressions for wrong-question execution."""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.intent.models import IntentSpec, IntentType, TurnRelation
from backend.app.intent.question_router import QuestionRouter
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.memory.models import RuntimeDataMode
from backend.app.query_plan.grounding import CandidateSelection
from backend.app.query_plan.turn_relation import TurnRelationEvidence, TurnRelationKind
from backend.app.schemas.data_contracts import QueryPlan, QueryResult, QueryShape, StructuredFilter
from backend.tests.api.test_chat import (
    _M533MultiTurnAdapter,
    _deepseek_test_profile,
    _patch_fake_runtime_glossary,
)


class _SemanticSafetyProvider(LLMProvider):
    """Script only language drafts; runtime catalog remains semantic authority."""

    provider_name = "m5103-language"
    is_mock = False

    def __init__(self) -> None:
        self.active = "p0_a"
        self.message_override: str | None = None
        self.calls: list[LLMRequest] = []

    async def generate(self, request, output_type):
        self.calls.append(request)
        if request.task == LLMTask.SEMANTIC_SELECTION:
            content = request.messages[-1]["content"]
            if "角色：measure" in content and "最挣钱" in content:
                selected = CandidateSelection(
                    outcome="RESOLVED",
                    candidate_id="measure:Sales:Total Sales",
                    matched_phrase="最挣钱",
                )
            elif "角色：ranking_dimension" in content and "产品" in content:
                selected = CandidateSelection(
                    outcome="RESOLVED",
                    candidate_id="field:Sales:Product",
                    matched_phrase="产品",
                )
            else:
                selected = CandidateSelection(outcome="UNRESOLVED")
            return LLMResponse(
                content="{}", structured=selected, model="offline-language"
            )

        if request.task == LLMTask.INTENT_RECOGNITION:
            structured = self._intent()
        elif request.task == LLMTask.QUERY_PLAN:
            structured = self._plan()
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="offline-language",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    def _intent(self) -> IntentSpec:
        values: dict[str, object] = {
            "intent": IntentType.DATA_QUESTION,
            "confidence": 0.99,
            "normalized_question": self._message(),
        }
        if self.active == "p0_a":
            values.update(
                detected_measures=["最挣钱"],
                detected_dimensions=["哪三个产品"],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
        elif self.active in {"south_seed", "rank_south_product"}:
            values.update(
                detected_measures=["销售额"],
                detected_filters=[
                    {"field": "区域", "operator": "eq", "value": "华南"}
                ],
                turn_relation=TurnRelation.FRESH_QUESTION,
            )
            if self.active == "rank_south_product":
                values["detected_dimensions"] = ["产品"]
        elif self.active in {"rank_region", "pending_rank"}:
            values.update(
                detected_dimensions=["区域" if self.active == "rank_region" else "产品"],
                turn_relation=TurnRelation.FOLLOW_UP,
            )
        elif self.active in {"correct_measure", "correct_measure_ranking"}:
            values.update(
                detected_measures=["销售数量"],
                turn_relation=TurnRelation.REPLACE,
            )
            if self.active == "correct_measure_ranking":
                values["detected_dimensions"] = ["产品"]
        elif self.active in {"correct_region", "unknown_region"}:
            values.update(
                detected_filters=[{
                    "field": "区域",
                    "operator": "eq",
                    "value": "华北" if self.active == "correct_region" else "火星区",
                }],
                turn_relation=TurnRelation.REPLACE,
            )
        else:  # pragma: no cover - fixture exhaustiveness
            raise AssertionError(self.active)
        return IntentSpec.model_validate(values)

    def _plan(self) -> QueryPlan:
        values: dict[str, object] = {
            "normalized_question": self._message(),
            "semantic_model_key": "local_desktop_model",
        }
        if self.active == "p0_a":
            values.update(
                query_shape=QueryShape.RANKING,
                measures=["Total Sales"],
                dimensions=["Product"],
                sort="desc",
                top_n=3,
            )
        elif self.active == "south_seed":
            values.update(
                query_shape=QueryShape.SCALAR,
                measures=["Total Sales"],
                filters=[StructuredFilter(field="Region", value="华南")],
            )
        elif self.active == "rank_region":
            values.update(
                query_shape=QueryShape.RANKING,
                dimensions=["Region"],
                sort="desc",
                top_n=1,
            )
        elif self.active == "rank_south_product":
            values.update(
                query_shape=QueryShape.RANKING,
                measures=["Total Sales"],
                dimensions=["Product"],
                filters=[StructuredFilter(field="Region", value="华南")],
                sort="desc",
                top_n=1,
            )
        elif self.active == "pending_rank":
            values.update(
                query_shape=QueryShape.RANKING,
                dimensions=["Product"],
                sort="desc",
                top_n=1,
            )
        elif self.active == "correct_measure":
            values["measures"] = ["Total Quantity"]
        elif self.active == "correct_measure_ranking":
            values.update(
                query_shape=QueryShape.RANKING,
                query_shape_evidence="按产品排前三",
                measures=["Total Quantity"],
                dimensions=["Product"],
                sort="desc",
                top_n=3,
            )
        elif self.active in {"correct_region", "unknown_region"}:
            values["filters"] = [StructuredFilter(
                field="Region",
                value="华北" if self.active == "correct_region" else "火星区",
            )]
        else:  # pragma: no cover - fixture exhaustiveness
            raise AssertionError(self.active)
        return QueryPlan.model_validate(values)

    def _message(self) -> str:
        return self.message_override or {
            "p0_a": "哪三个产品最挣钱",
            "south_seed": "华南区域的销售额是多少？",
            "rank_region": "哪个区域卖得最好？",
            "rank_south_product": "华南销售额最高的前3个产品是什么？",
            "pending_rank": "哪个产品卖得最好？",
            "correct_measure": "不是销售额，是销售数量",
            "correct_measure_ranking": "不是销售额，是销售数量，按产品排前三",
            "correct_region": "也不是华南，是华北",
            "unknown_region": "也不是华南，是火星区",
        }[self.active]


class _SemanticSafetyAdapter(_M533MultiTurnAdapter):
    async def execute_dax(self, request):
        result = await super().execute_dax(request)
        match = re.search(r"TOPN\(\s*(\d+)", request.dax)
        if match and not result.error:
            rows = result.rows[: int(match.group(1))]
            return result.model_copy(update={"rows": rows, "row_count": len(rows)})
        return result


def _create_app(monkeypatch):
    import backend.app.llm.factory as llm_factory
    import backend.app.main as main_module

    provider = _SemanticSafetyProvider()
    registry = LLMProviderRegistry()
    registry.register(_deepseek_test_profile(), provider)
    monkeypatch.setattr(llm_factory, "build_llm_registry", lambda settings: registry)
    _patch_fake_runtime_glossary(monkeypatch)
    monkeypatch.setattr(main_module, "LocalMCPPowerBIAdapter", _SemanticSafetyAdapter)
    app = main_module.create_app(settings=Settings(
        _env_file=None,
        llm_mode=LLMMode.DEEPSEEK,
        powerbi_mode=PowerBIMode.LOCAL_MCP,
        deepseek_api_key="test-key-not-real",
    ))
    return app, provider


async def _post(client: AsyncClient, provider: _SemanticSafetyProvider, active: str, conversation_id: str):
    provider.active = active
    return await client.post("/api/v1/chat", json={
        "message": provider._message(),
        "conversation_id": conversation_id,
        "request_id": f"m5103-{active}-{uuid.uuid4()}",
        "semantic_model_key": "local_desktop_model",
    })


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    ["哪三个产品最挣钱", "哪3个产品最挣钱？", "哪三个产品最赚钱？"],
)
async def test_ranking_draft_cannot_be_silently_downgraded_to_scalar(
    monkeypatch, message: str
):
    assert QuestionRouter().route(message).query_shape == QueryShape.SCALAR
    app, provider = _create_app(monkeypatch)
    provider.message_override = message

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _post(client, provider, "p0_a", "m5103-p0-a")
        memory = await service.pipeline.get_latest_committed_memory(
            "m5103-p0-a", RuntimeDataMode.REAL
        )

    body = response.json()
    assert response.status_code == 200, body
    assert body["terminal_state"] == "clarification_required", body
    assert body["memory_commit"] is False
    assert service.powerbi.dax_calls == 0
    assert memory is None
    assert body["execution_audit"]["grounded_delta"]["query_shape"] == "ranking"


@pytest.mark.asyncio
async def test_same_field_filter_is_removed_when_current_turn_ranks_that_field(monkeypatch):
    app, provider = _create_app(monkeypatch)
    conversation_id = "m5103-p0-b"

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            seeded = (await _post(client, provider, "south_seed", conversation_id)).json()
            ranked = (await _post(client, provider, "rank_region", conversation_id)).json()
        memory = await service.pipeline.get_latest_committed_memory(
            conversation_id, RuntimeDataMode.REAL
        )

    assert seeded["terminal_state"] == "completed", seeded
    assert seeded["execution_audit"]["canonical_query_plan"]["filters"] == [{
        "field": "Region", "operator": "eq", "value": "华南"
    }]
    assert ranked["terminal_state"] == "completed", ranked
    plan = ranked["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "ranking"
    assert plan["dimensions"] == ["Region"]
    assert plan["filters"] == []
    assert ranked["execution_audit"]["removed_inherited_filter_fields"] == [
        "Region"
    ]
    assert "filters" not in ranked["execution_audit"]["inherited_slots"]
    assert service.powerbi.dax_calls == 2
    assert memory is not None and memory.memory_version == 2
    assert memory.filters == []


@pytest.mark.asyncio
async def test_correction_chain_replaces_current_slots_without_losing_ranking(monkeypatch):
    assert TurnRelationEvidence.classify(
        "不是销售额，是销售数量"
    ).kind == TurnRelationKind.REPLACE
    assert TurnRelationEvidence.classify(
        "也不是华南，是华北"
    ).kind == TurnRelationKind.REPLACE
    app, provider = _create_app(monkeypatch)
    conversation_id = "m5103-p0-c"

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            seeded = (await _post(client, provider, "rank_south_product", conversation_id)).json()
            measure = (await _post(client, provider, "correct_measure", conversation_id)).json()
            region = (await _post(client, provider, "correct_region", conversation_id)).json()
        memory = await service.pipeline.get_latest_committed_memory(
            conversation_id, RuntimeDataMode.REAL
        )

    assert seeded["terminal_state"] == "completed", seeded
    assert measure["terminal_state"] == "completed", measure
    measure_plan = measure["execution_audit"]["canonical_query_plan"]
    assert measure_plan["query_shape"] == "ranking"
    assert measure_plan["measures"] == ["Total Quantity"]
    assert measure_plan["dimensions"] == ["Product"]
    assert measure_plan["filters"][0]["value"] == "华南"
    assert measure_plan["sort"] == "desc" and measure_plan["top_n"] == 3

    assert region["terminal_state"] == "completed", region
    region_plan = region["execution_audit"]["canonical_query_plan"]
    assert region_plan["query_shape"] == "ranking"
    assert region_plan["measures"] == ["Total Quantity"]
    assert region_plan["dimensions"] == ["Product"]
    assert region_plan["filters"][0]["value"] == "华北"
    assert region_plan["sort"] == "desc" and region_plan["top_n"] == 3
    assert service.powerbi.dax_calls == 3
    assert memory is not None and memory.memory_version == 3
    assert memory.measures == ["Total Quantity"]
    assert memory.filters[0]["value"] == "华北"


@pytest.mark.asyncio
async def test_correction_completes_pending_ranking_before_committed_memory(monkeypatch):
    app, provider = _create_app(monkeypatch)
    conversation_id = "m5103-p0-c-pending"

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            pending_response = (
                await _post(client, provider, "pending_rank", conversation_id)
            ).json()
            pending = await service.pipeline.get_pending_clarification(
                conversation_id, RuntimeDataMode.REAL
            )
            correction = (
                await _post(client, provider, "correct_measure", conversation_id)
            ).json()
        committed = await service.pipeline.get_latest_committed_memory(
            conversation_id, RuntimeDataMode.REAL
        )

    assert pending_response["terminal_state"] == "clarification_required"
    assert pending_response["memory_commit"] is False
    assert pending is not None
    assert pending.query_shape == QueryShape.RANKING
    assert pending.dimensions == ["Product"]
    assert pending.sort == "desc" and pending.top_n == 1
    assert correction["terminal_state"] == "completed", correction
    plan = correction["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "ranking"
    assert plan["measures"] == ["Total Quantity"]
    assert plan["dimensions"] == ["Product"]
    assert plan["sort"] == "desc" and plan["top_n"] == 1
    assert service.powerbi.dax_calls == 1
    assert committed is not None and committed.memory_version == 1


@pytest.mark.asyncio
async def test_current_correction_ranking_draft_precedes_committed_scalar(monkeypatch):
    app, provider = _create_app(monkeypatch)
    conversation_id = "m5103-p0-c-current-draft"

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            seeded = (await _post(client, provider, "south_seed", conversation_id)).json()
            corrected = (
                await _post(
                    client,
                    provider,
                    "correct_measure_ranking",
                    conversation_id,
                )
            ).json()

    assert seeded["terminal_state"] == "completed", seeded
    assert corrected["terminal_state"] == "completed", corrected
    plan = corrected["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "ranking"
    assert plan["measures"] == ["Total Quantity"]
    assert plan["dimensions"] == ["Product"]
    assert plan["filters"] == [{
        "field": "Region", "operator": "eq", "value": "华南"
    }]
    assert plan["sort"] == "desc" and plan["top_n"] == 3
    assert service.powerbi.dax_calls == 2


@pytest.mark.asyncio
async def test_unknown_member_correction_is_zero_dax_and_keeps_committed_state(monkeypatch):
    app, provider = _create_app(monkeypatch)
    conversation_id = "m5103-p0-c-unknown"

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            seeded = (await _post(client, provider, "rank_south_product", conversation_id)).json()
            before_calls = service.powerbi.dax_calls
            failed = (await _post(client, provider, "unknown_region", conversation_id)).json()
        memory = await service.pipeline.get_latest_committed_memory(
            conversation_id, RuntimeDataMode.REAL
        )

    assert seeded["terminal_state"] == "completed", seeded
    assert failed["terminal_state"] == "clarification_required", failed
    assert failed["memory_commit"] is False
    assert service.powerbi.dax_calls == before_calls
    assert memory is not None and memory.memory_version == 1
    assert memory.filters[0]["value"] == "华南"
