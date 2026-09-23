"""M5.10.6 manual-acceptance failure corpus.

These tests intentionally describe the reopened target contract.  They must be
RED on the published ``main@276d67d`` baseline before production is changed.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.facts import FactBoundedAnswerBuilder, VerifiedFactSetBuilder
from backend.app.intent.models import TimeIntentDraft, TimeIntentKind, TurnRelation
from backend.app.intent.question_router import QuestionRoute, QuestionRouter
from backend.app.intent.semantic_interpreter import (
    AnalysisGoal,
    LLMSemanticInterpreter,
    RankingIntent,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticCoverageDecision,
    SemanticFilterMention,
    SemanticInterpretationError,
    SemanticInterpretationMode,
)
from backend.app.llm.base import LLMProvider, LLMRequest, LLMResponse
from backend.app.query_plan.grounding import (
    BoundedLLMObjectSelector,
    CandidateSelection,
    GroundingStatus,
    SemanticEquivalenceVeto,
    SemanticGroundingService,
)
from backend.app.query_plan.semantic_catalog import (
    CatalogObject,
    SemanticCatalog,
    SemanticObjectType,
)
from backend.app.schemas.data_contracts import (
    CanonicalQueryPlan,
    ColumnMembersResult,
    QueryResult,
    QueryShape,
    StructuredFilter,
    TimeRangeMode,
    TimeRangeSpec,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class _FrameProvider(LLMProvider):
    def __init__(self, frame: SemanticFrame) -> None:
        self.frame = frame
        self.calls: list[LLMRequest] = []

    async def generate(self, request, output_type):
        self.calls.append(request)
        if output_type is SemanticFrame:
            structured = self.frame
        else:
            assert output_type is SemanticCoverageDecision
            payload = json.loads(request.messages[-1]["content"])
            represented = {
                item["text"] for item in payload["semantic_frame"]["evidence_spans"]
            }
            structured = (
                SemanticCoverageDecision(
                    decision="MISSING_SEMANTIC_SPAN", missing_span="华南"
                )
                if "华南" in payload["current_user_message"]
                and "华南" not in represented
                else SemanticCoverageDecision(decision="ACCEPT")
            )
        return LLMResponse(content="{}", structured=structured, model="failure-corpus")

    @property
    def provider_name(self) -> str:
        return "failure-corpus"

    @property
    def is_mock(self) -> bool:
        return False


class _MemberChoiceProvider(LLMProvider):
    def __init__(self, chosen_value: str, *, echo_evidence: bool = True) -> None:
        self.chosen_value = chosen_value
        self.echo_evidence = echo_evidence
        self.calls: list[LLMRequest] = []

    async def generate(self, request, output_type):
        self.calls.append(request)
        content = request.messages[-1]["content"]
        if output_type is SemanticEquivalenceVeto:
            payload = json.loads(content)
            return LLMResponse(
                content="{}",
                structured=SemanticEquivalenceVeto(
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
                ),
                model="failure-corpus",
            )
        if not content.startswith("{"):
            phrase = content.split(
                "\n当前输入：", 1
            )[0].split("当前短语：", 1)[-1]
            return LLMResponse(
                content="{}",
                structured=CandidateSelection(
                    outcome="RESOLVED",
                    candidate_id="field:Sales:Region",
                    matched_phrase=phrase,
                ),
                model="failure-corpus",
            )
        payload = json.loads(content)
        candidate_id = next(
            item["candidate_id"]
            for item in payload["candidates"]
            if item["value"] == self.chosen_value
        )
        return LLMResponse(
            content="{}",
            structured=CandidateSelection(
                outcome="RESOLVED",
                candidate_id=candidate_id,
                matched_phrase=(
                    payload["requested_value"] if self.echo_evidence else None
                ),
            ),
            model="failure-corpus",
        )

    @property
    def provider_name(self) -> str:
        return "failure-corpus"

    @property
    def is_mock(self) -> bool:
        return False


async def _interpret(question: str, frame: SemanticFrame) -> SemanticFrame:
    return await LLMSemanticInterpreter(_FrameProvider(frame)).interpret(question)


def _region_field() -> CatalogObject:
    return CatalogObject(
        object_id="field:Sales:Region",
        canonical_name="Region",
        object_type=SemanticObjectType.FIELD,
        table_name="Sales",
        data_type="string",
    )


def _region_members() -> ColumnMembersResult:
    return ColumnMembersResult(
        semantic_model_key="model",
        table_name="Sales",
        field_name="Region",
        values=["North", "South", "East", "West"],
        source_mode="real",
    )


def _grounding_catalog() -> SemanticCatalog:
    return SemanticCatalog(
        semantic_model_key="model",
        schema_fingerprint="0" * 64,
        objects=(
            CatalogObject(
                object_id="measure:Sales:Total Sales",
                canonical_name="Total Sales",
                object_type=SemanticObjectType.MEASURE,
                table_name="Sales",
                data_type="decimal",
                aliases=("销售额",),
            ),
            _region_field().model_copy(update={"aliases": ("地区",)}),
        ),
    )


def test_a_general_location_recommendation_is_not_router_business_semantics() -> None:
    decision = QuestionRouter().route("我公司在深圳岗厦北，有什么推荐？")

    assert decision.route is QuestionRoute.LLM_SEMANTIC_INTERPRETATION
    assert decision.query_shape is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mention", ["南方", "华南", "华南地区"])
async def test_b_member_language_linking_is_generic_and_runtime_bounded(
    mention: str,
) -> None:
    provider = _MemberChoiceProvider("South")
    result = await BoundedLLMObjectSelector(provider).select_member(
        mention,
        _region_field(),
        _region_members(),
        user_input=f"2025年5月{mention}销售额是多少",
    )

    assert result.status is GroundingStatus.RESOLVED
    assert result.canonical_value == "South"
    prompt = provider.calls[0].messages[0]["content"].casefold()
    assert "compass-direction" not in prompt
    assert "directional region" not in prompt
    assert "south" not in prompt
    veto_prompt = provider.calls[-1].messages[0]["content"].casefold()
    assert "south" not in veto_prompt
    assert "华南" not in veto_prompt
    glossary = (REPO_ROOT / "backend/app/query_plan/business_glossary.yaml").read_text(
        encoding="utf-8"
    )
    assert "华南: South" not in glossary
    assert "南区: South" not in glossary


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", ["火星区", "深圳"])
async def test_c_unknown_or_entity_to_category_member_mapping_fails_closed(
    unknown: str,
) -> None:
    malicious_selector = _MemberChoiceProvider("South", echo_evidence=True)
    result = await BoundedLLMObjectSelector(malicious_selector).select_member(
        unknown,
        _region_field(),
        _region_members(),
        user_input=f"{unknown}销售额是多少",
    )

    assert result.status is GroundingStatus.UNRESOLVED
    assert result.canonical_value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mention", "echo_evidence", "expected"),
    [("华南", True, GroundingStatus.RESOLVED), ("火星区", False, GroundingStatus.UNRESOLVED)],
)
async def test_c_ground_frame_binds_only_runtime_verified_members(
    mention: str,
    echo_evidence: bool,
    expected: GroundingStatus,
) -> None:
    service = SemanticGroundingService(
        _grounding_catalog(),
        selector=BoundedLLMObjectSelector(
            _MemberChoiceProvider("South", echo_evidence=echo_evidence)
        ),
    )
    frame = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        member_mentions=(mention,),
        filter_mentions=(
            SemanticFilterMention(
                field_mention=None,
                member_mention=mention,
                evidence_span=mention,
            ),
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="是多少"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="member", text=mention),
            SemanticEvidenceSpan(slot="filter", text=mention),
        ),
    )

    async def lookup(_field, _limit):
        return _region_members()

    outcome = await service.ground_frame(
        f"{mention}销售额是多少", frame, None, lookup
    )

    assert outcome.status is expected
    if expected is GroundingStatus.RESOLVED:
        assert outcome.delta is not None
        assert outcome.delta.filters == [
            StructuredFilter(field="Region", value="South")
        ]
    else:
        # Verified slots may be retained only in non-executable pending state;
        # the unknown member itself never becomes a canonical filter.
        assert outcome.delta is not None
        assert outcome.delta.measures == ["Total Sales"]
        assert not outcome.delta.filters
        assert all(
            item.status is not GroundingStatus.RESOLVED
            for item in outcome.member_results
        )


@pytest.mark.asyncio
async def test_d_generic_sales_does_not_accept_hallucinated_ranking_shape() -> None:
    question = "2026年销售情况"
    draft = await _interpret(
        question,
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=None,
            time_mentions=("2026年",),
            time_intent=TimeIntentDraft(
                kind=TimeIntentKind.ABSOLUTE_YEAR,
                expression="2026年",
                year=2026,
            ),
            unresolved_mentions=("销售",),
            evidence_spans=(
                SemanticEvidenceSpan(slot="time", text="2026年"),
                SemanticEvidenceSpan(slot="unresolved", text="销售"),
            ),
        ),
    )

    frame = draft.model_dump(mode="json")
    assert frame["query_shape"] is None
    assert frame["measure_mentions"] == []
    assert frame["unresolved_mentions"] == ["销售"]
    assert "query_plan" not in frame


@pytest.mark.asyncio
async def test_d_adversarial_scalar_to_ranking_requires_ranking_structure() -> None:
    question = "2026年销售额情况"
    hallucinated = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.RANKING,
        measure_mentions=("销售额",),
        time_mentions=("2026年",),
        time_intent=TimeIntentDraft(
            kind=TimeIntentKind.ABSOLUTE_YEAR,
            expression="2026年",
            year=2026,
        ),
        ranking_intent=RankingIntent(
            direction="desc",
            top_n=3,
            evidence_span="销售额情况",
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额情况"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="time", text="2026年"),
            SemanticEvidenceSpan(slot="ranking", text="销售额情况"),
        ),
    )

    with pytest.raises(SemanticInterpretationError):
        await _interpret(question, hallucinated)


@pytest.mark.asyncio
async def test_d_omitted_region_filter_is_coverage_failure() -> None:
    question = "2026年华南销售额是多少"
    omitted_filter = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        time_mentions=("2026年",),
        time_intent=TimeIntentDraft(
            kind=TimeIntentKind.ABSOLUTE_YEAR,
            expression="2026年",
            year=2026,
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="是多少"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="time", text="2026年"),
        ),
    )

    with pytest.raises(SemanticInterpretationError):
        await _interpret(question, omitted_filter)


@pytest.mark.asyncio
async def test_d_filter_field_evidence_cannot_be_invented_outside_current_message() -> None:
    question = "华南销售额是多少"
    forged_field = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        member_mentions=("华南",),
        filter_mentions=(
            SemanticFilterMention(
                field_mention="地区",
                member_mention="华南",
                evidence_span="华南",
            ),
        ),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="是多少"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
            SemanticEvidenceSpan(slot="member", text="华南"),
            SemanticEvidenceSpan(slot="filter", text="华南"),
        ),
    )

    with pytest.raises(SemanticInterpretationError):
        await _interpret(question, forged_field)


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["2026年销售额情况", "今年销售额"])
async def test_e_clear_scalar_is_a_language_frame_not_a_query_plan(question: str) -> None:
    time_text = "2026年" if "2026" in question else "今年"
    draft = await _interpret(
        question,
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=QueryShape.SCALAR,
            measure_mentions=("销售额",),
            time_mentions=(time_text,),
            time_intent=TimeIntentDraft(
                kind=(
                    TimeIntentKind.ABSOLUTE_YEAR
                    if "2026" in question
                    else TimeIntentKind.RELATIVE_YEAR
                ),
                expression=time_text,
                year=2026 if "2026" in question else None,
                relative_offset=0 if "2026" not in question else None,
            ),
            evidence_spans=(
                SemanticEvidenceSpan(slot="query_shape", text="销售额"),
                SemanticEvidenceSpan(slot="measure", text="销售额"),
                SemanticEvidenceSpan(slot="time", text=time_text),
            ),
        ),
    )

    frame = draft.model_dump(mode="json")
    assert frame["query_shape"] == QueryShape.SCALAR.value
    assert frame["measure_mentions"] == ["销售额"]
    assert frame["evidence_spans"]
    assert "query_plan" not in frame


@pytest.mark.asyncio
async def test_f_slot_only_measure_change_is_understanding_owned_follow_up() -> None:
    frame = await _interpret(
        "按销售额",
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            relation=TurnRelation.FOLLOW_UP,
            query_shape=QueryShape.SCALAR,
            measure_mentions=("销售额",),
            changed_slots=("measure",),
            referenced_context_slots=("time", "filters"),
            evidence_spans=(
                SemanticEvidenceSpan(slot="relation", text="按"),
                SemanticEvidenceSpan(slot="query_shape", text="销售额"),
                SemanticEvidenceSpan(slot="measure", text="销售额"),
            ),
        ),
    )

    assert frame.relation is TurnRelation.FOLLOW_UP
    assert frame.changed_slots == ("measure",)
    assert frame.referenced_context_slots == ("time", "filters")


@pytest.mark.asyncio
async def test_g_why_decline_is_explain_change_not_a_filter_guess() -> None:
    question = "帮我分析当前报表里今年销售额为什么下降"
    draft = await _interpret(
        question,
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=QueryShape.SCALAR,
            measure_mentions=("销售额",),
            time_mentions=("今年",),
            time_intent=TimeIntentDraft(
                kind=TimeIntentKind.RELATIVE_YEAR,
                expression="今年",
                relative_offset=0,
            ),
            analysis_goal=AnalysisGoal.EXPLAIN_CHANGE,
            evidence_spans=(
                SemanticEvidenceSpan(slot="query_shape", text="销售额"),
                SemanticEvidenceSpan(slot="measure", text="销售额"),
                SemanticEvidenceSpan(slot="time", text="今年"),
            ),
        ),
    )

    frame = draft.model_dump(mode="json")
    assert frame["analysis_goal"] == "EXPLAIN_CHANGE"
    assert frame["filter_mentions"] == []
    assert frame["measure_mentions"] == ["销售额"]
    assert frame["time_mentions"] == ["今年"]
    assert "query_plan" not in frame


def test_h_verified_answer_uses_user_facing_member_language() -> None:
    plan = CanonicalQueryPlan(
        normalized_question="2025年5月南方销售额是多少",
        semantic_model_key="model",
        query_shape=QueryShape.SCALAR,
        measures=["Total Sales"],
        filters=[StructuredFilter(field="Region", value="South")],
        time_range=TimeRangeSpec(
            date_field="Order Date",
            start_date=date(2025, 5, 1),
            end_date=date(2025, 5, 31),
            mode=TimeRangeMode.EXPLICIT_RANGE,
            grain="month",
        ),
    )
    result = QueryResult(
        result_id="failure-corpus-result",
        semantic_model_key="model",
        columns=["[Total Sales]"],
        rows=[[197199.61]],
        row_count=1,
        source_mode="real",
    )
    facts = VerifiedFactSetBuilder().build(plan, result)
    answer = FactBoundedAnswerBuilder().build(
        plan,
        result,
        facts,
        display_bindings={
            "[Total Sales]": SimpleNamespace(
                canonical_name="Total Sales",
                display_name="销售额",
                format_kind=None,
            )
        },
        user_facing_filter_values={("Region", "South"): "南方"},
    )

    assert "销售额" in answer.answer
    assert "南方" in answer.answer
    assert "Total Sales" not in answer.answer
    assert "Region=South" not in answer.answer
    assert "South" not in answer.answer
