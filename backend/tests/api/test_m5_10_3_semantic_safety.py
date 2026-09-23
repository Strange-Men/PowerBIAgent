"""M5.10.3 production-path regressions for wrong-question execution."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config.settings import LLMMode, PowerBIMode, Settings
from backend.app.intent.models import TurnRelation
from backend.app.intent.semantic_interpreter import (
    GeneralFactScope,
    RankingIntent,
    SemanticCoverageDecision,
    SemanticEvidenceSpan,
    SemanticFilterMention,
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.intent.question_router import QuestionRouter
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMTask
from backend.app.llm.registry import LLMProviderRegistry
from backend.app.memory.models import RuntimeDataMode
from backend.app.query_plan.grounding import CandidateSelection, SemanticEquivalenceVeto
from backend.app.schemas.data_contracts import QueryResult, QueryShape
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
        if request.task is LLMTask.UNDERSTANDING:
            structured = self._frame()
        elif request.task is LLMTask.UNDERSTANDING_COVERAGE:
            structured = SemanticCoverageDecision(decision="ACCEPT")
        elif request.task is LLMTask.SEMANTIC_SELECTION:
            content = request.messages[-1]["content"]
            if "角色：measure" in content and "最挣钱" in content:
                structured = CandidateSelection(outcome="UNRESOLVED")
            elif "角色：ranking_dimension" in content and "产品" in content:
                structured = CandidateSelection(
                    outcome="RESOLVED",
                    candidate_id="field:Sales:Product",
                    matched_phrase="产品",
                )
            elif "角色：filter_field" in content and any(
                item in content for item in ("华南", "华北", "火星区")
            ):
                phrase = content.partition("当前短语：")[2].partition("\n当前输入：")[0]
                structured = CandidateSelection(
                    outcome="RESOLVED",
                    candidate_id="field:Sales:Region",
                    matched_phrase=phrase,
                )
            else:
                structured = CandidateSelection(outcome="UNRESOLVED")
        elif request.task is LLMTask.SEMANTIC_EQUIVALENCE_VETO:
            payload = json.loads(request.messages[-1]["content"])
            structured = SemanticEquivalenceVeto(
                decision=(
                    "REJECT"
                    if payload["requested_literal"] in {"深圳", "火星区"}
                    else "ACCEPT"
                ),
                mismatch=(
                    "PROPER_ENTITY"
                    if payload["requested_literal"] in {"深圳", "火星区"}
                    else "NONE"
                ),
            )
        else:
            raise AssertionError(f"unexpected LLM task: {request.task}")
        return LLMResponse(
            content="{}",
            structured=structured,
            model="offline-language",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    def _frame(self) -> SemanticFrame:
        message = self._message()
        if self.active == "general":
            return SemanticFrame(
                mode=SemanticInterpretationMode.GENERAL,
                general_fact_scope=GeneralFactScope.TIME_STABLE_OR_NONFACTUAL,
                general_answer="复盘可以帮助识别偏差并沉淀经验。",
            )

        relation = TurnRelation.FRESH_QUESTION
        shape = None
        measures: tuple[str, ...] = ()
        dimensions: tuple[str, ...] = ()
        filters: tuple[SemanticFilterMention, ...] = ()
        members: tuple[str, ...] = ()
        ranking = None
        changed: tuple[str, ...] = ()
        referenced: tuple[str, ...] = ()
        spans: list[SemanticEvidenceSpan] = []

        if self.active == "p0_a":
            shape = QueryShape.RANKING
            measures = (("最赚钱" if "最赚钱" in message else "最挣钱"),)
            dimensions = ("产品",)
            ranking = RankingIntent(
                direction="desc",
                top_n=3,
                evidence_span=("三个" if "三个" in message else "3个"),
            )
        elif self.active == "south_seed":
            shape = QueryShape.SCALAR
            measures = ("销售额",)
            members = ("华南",)
            filters = (SemanticFilterMention(
                field_mention="区域", member_mention="华南", evidence_span="华南"
            ),)
        elif self.active == "rank_region":
            relation = TurnRelation.FOLLOW_UP
            shape = QueryShape.RANKING
            dimensions = ("区域",)
            ranking = RankingIntent(direction="desc", top_n=1, evidence_span="最好")
            changed = ("query_shape", "dimension", "ranking")
            referenced = ("measure", "filters")
        elif self.active == "rank_south_product":
            shape = QueryShape.RANKING
            measures = ("销售额",)
            dimensions = ("产品",)
            members = ("华南",)
            filters = (SemanticFilterMention(
                field_mention=None, member_mention="华南", evidence_span="华南"
            ),)
            ranking = RankingIntent(direction="desc", top_n=3, evidence_span="最高的前3个")
        elif self.active == "pending_rank":
            relation = TurnRelation.FOLLOW_UP
            shape = QueryShape.RANKING
            dimensions = ("产品",)
            ranking = RankingIntent(direction="desc", top_n=1, evidence_span="最好")
            changed = ("query_shape", "dimension", "ranking")
            referenced = ("measure",)
        elif self.active in {"correct_measure", "correct_measure_ranking"}:
            relation = TurnRelation.REPLACE
            measures = ("销售数量",)
            changed = ("measure",)
            referenced = ("query_shape", "dimension", "filter", "ranking")
            if self.active == "correct_measure_ranking":
                shape = QueryShape.RANKING
                dimensions = ("产品",)
                ranking = RankingIntent(direction="desc", top_n=3, evidence_span="排前三")
                changed = ("measure", "query_shape", "dimension", "ranking")
        elif self.active == "complete_measure":
            relation = TurnRelation.FOLLOW_UP
            measures = ("销售额",)
            changed = ("measure",)
            referenced = ("query_shape", "dimension", "ranking")
        elif self.active in {"correct_region", "unknown_region"}:
            relation = TurnRelation.REPLACE
            value = "华北" if self.active == "correct_region" else "火星区"
            members = (value,)
            filters = (SemanticFilterMention(
                field_mention=None, member_mention=value, evidence_span=value
            ),)
            changed = ("filter",)
            referenced = ("query_shape", "measure", "dimension", "ranking")
        else:
            raise AssertionError(self.active)

        if shape is not None:
            spans.append(SemanticEvidenceSpan(slot="query_shape", text=message))
        spans.extend(SemanticEvidenceSpan(slot="measure", text=item) for item in measures)
        spans.extend(SemanticEvidenceSpan(slot="dimension", text=item) for item in dimensions)
        spans.extend(SemanticEvidenceSpan(slot="member", text=item) for item in members)
        spans.extend(
            SemanticEvidenceSpan(slot="filter", text=item.evidence_span)
            for item in filters
        )
        if ranking is not None:
            spans.append(SemanticEvidenceSpan(slot="ranking", text=ranking.evidence_span))
        return SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            relation=relation,
            query_shape=shape,
            measure_mentions=measures,
            dimension_mentions=dimensions,
            member_mentions=members,
            filter_mentions=filters,
            ranking_intent=ranking,
            changed_slots=changed,
            referenced_context_slots=referenced,
            evidence_spans=tuple(spans),
        )

    def _message(self) -> str:
        return self.message_override or {
            "p0_a": "哪三个产品最挣钱",
            "south_seed": "华南区域的销售额是多少？",
            "rank_region": "哪个区域卖得最好？",
            "rank_south_product": "华南销售额最高的前3个产品是什么？",
            "pending_rank": "哪个产品卖得最好？",
            "correct_measure": "不是销售额，是销售数量",
            "complete_measure": "按销售额",
            "correct_measure_ranking": "不是销售额，是销售数量，按产品排前三",
            "correct_region": "也不是华南，是华北",
            "unknown_region": "也不是华南，是火星区",
            "general": "顺便说说，为什么复盘有用？",
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
    routing = QuestionRouter().route(message)
    assert routing.route.value == "llm_semantic_interpretation"
    assert routing.query_shape is None
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
    assert body["execution_audit"]["semantic_frame"]["query_shape"] == "ranking"


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

    assert seeded["terminal_state"] == "completed", (
        seeded.get("execution_audit", {}).get("clarification_reason"),
        seeded.get("execution_audit", {}).get("object_grounding_status"),
        seeded.get("execution_audit", {}).get("member_grounding_status"),
    )
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
    app, provider = _create_app(monkeypatch)
    provider.active = "correct_measure"
    assert provider._frame().relation is TurnRelation.REPLACE
    provider.active = "correct_region"
    assert provider._frame().relation is TurnRelation.REPLACE
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

    assert seeded["terminal_state"] == "completed", (
        seeded.get("execution_audit", {}).get("clarification_reason"),
        seeded.get("execution_audit", {}).get("object_grounding_status"),
        seeded.get("execution_audit", {}).get("member_grounding_status"),
    )
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
    assert correction["terminal_state"] == "completed", correction.get(
        "execution_audit"
    )
    plan = correction["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "ranking"
    assert plan["measures"] == ["Total Quantity"]
    assert plan["dimensions"] == ["Product"]
    assert plan["sort"] == "desc" and plan["top_n"] == 1
    assert service.powerbi.dax_calls == 1
    assert committed is not None and committed.memory_version == 1


@pytest.mark.asyncio
async def test_general_turn_preserves_pending_ranking_for_slot_only_completion(monkeypatch):
    app, provider = _create_app(monkeypatch)
    conversation_id = "m5106-pending-general-complete"

    async with app.router.lifespan_context(app):
        service = app.state.turn_service
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            opened = (
                await _post(client, provider, "pending_rank", conversation_id)
            ).json()
            pending = await service.pipeline.get_pending_clarification(
                conversation_id, RuntimeDataMode.REAL
            )
            general = (
                await _post(client, provider, "general", conversation_id)
            ).json()
            pending_after_general = await service.pipeline.get_pending_clarification(
                conversation_id, RuntimeDataMode.REAL
            )
            completed = (
                await _post(client, provider, "complete_measure", conversation_id)
            ).json()

    assert opened["terminal_state"] == "clarification_required"
    assert pending is not None
    assert pending.query_shape is QueryShape.RANKING
    assert pending.dimensions == ["Product"]
    assert general["terminal_state"] == "completed"
    assert general["memory_commit"] is False
    assert pending_after_general is not None
    assert pending_after_general.chain_id == pending.chain_id
    assert pending_after_general.dimensions == ["Product"]
    assert completed["terminal_state"] == "completed", completed.get(
        "execution_audit"
    )
    plan = completed["execution_audit"]["canonical_query_plan"]
    assert plan["query_shape"] == "ranking"
    assert plan["measures"] == ["Total Sales"]
    assert plan["dimensions"] == ["Product"]
    assert plan["sort"] == "desc" and plan["top_n"] == 1
    assert service.powerbi.dax_calls == 1


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
