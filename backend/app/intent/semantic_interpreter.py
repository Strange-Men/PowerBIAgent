"""Single open-language interpretation authority for M5.10.6."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.app.answer.conversation import ConversationalAnswer, ConversationalAnswerService
from backend.app.intent.models import IntentSpec
from backend.app.llm.base import LLMProvider
from backend.app.query_plan.deepseek_service import DeepSeekQueryPlanService
from backend.app.report.deepseek_report_intent_service import (
    DeepSeekReportIntentService,
)
from backend.app.schemas.data_contracts import QueryPlan, QueryShape, SemanticModelSchema


class SemanticInterpretationMode(str, Enum):
    GENERAL = "general"
    BUSINESS = "business"
    REPORT = "report"


class SemanticInterpretationDraft(BaseModel):
    """Bounded language draft; every canonical slot remains runtime-owned."""

    mode: SemanticInterpretationMode
    query_shape_candidate: QueryShape | None = None
    measure_candidates: tuple[str, ...] = ()
    dimension_candidates: tuple[str, ...] = ()
    measure_evidence_spans: tuple[str, ...] = ()
    dimension_evidence_spans: tuple[str, ...] = ()
    raw_filter_phrases: tuple[str, ...] = ()
    raw_member_phrases: tuple[str, ...] = ()
    time_intent: str | None = None
    ranking_intent: dict[str, Any] | None = None
    comparison_intent: str | None = None
    report_section_candidates: tuple[str, ...] = ()
    evidence_spans: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()
    query_plan: QueryPlan | None = None
    answer: str = ""
    requires_business_grounding: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_conversation(cls, result: ConversationalAnswer) -> "SemanticInterpretationDraft":
        return cls(
            mode=(
                SemanticInterpretationMode.BUSINESS
                if result.requires_business_grounding
                else SemanticInterpretationMode.GENERAL
            ),
            answer=result.answer,
            requires_business_grounding=result.requires_business_grounding,
        )

    @classmethod
    def from_query_plan(
        cls,
        plan: QueryPlan,
        *,
        report: bool,
    ) -> "SemanticInterpretationDraft":
        filter_phrases = tuple(str(item.value) for item in plan.filters)
        evidence = tuple(item for item in (plan.query_shape_evidence,) if item)
        ranking = None
        if plan.query_shape is QueryShape.RANKING:
            ranking = {"sort": plan.sort, "top_n": plan.top_n}
        return cls(
            mode=(SemanticInterpretationMode.REPORT if report else SemanticInterpretationMode.BUSINESS),
            query_shape_candidate=plan.query_shape,
            measure_candidates=tuple(plan.measures),
            dimension_candidates=tuple(plan.dimensions),
            measure_evidence_spans=tuple(plan.measure_evidence_spans),
            dimension_evidence_spans=tuple(plan.dimension_evidence_spans),
            raw_filter_phrases=filter_phrases,
            raw_member_phrases=filter_phrases,
            time_intent=plan.time_range if isinstance(plan.time_range, str) else None,
            ranking_intent=ranking,
            comparison_intent=plan.comparison_mode,
            evidence_spans=evidence,
            query_plan=plan,
        )


class LLMSemanticInterpreter:
    """One logical authority with isolated general and schema-linked branches."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def interpret_general(self, user_input: str) -> SemanticInterpretationDraft:
        result = await ConversationalAnswerService(self._provider).generate(user_input)
        return SemanticInterpretationDraft.from_conversation(result)

    async def interpret_business(
        self,
        *,
        user_input: str,
        intent: IntentSpec,
        schema: SemanticModelSchema,
        committed_memory: dict[str, Any] | None,
        semantic_model_key: str,
        report_template_key: str | None,
        enforce_semantic_grounding: bool,
    ) -> SemanticInterpretationDraft:
        plan = await DeepSeekQueryPlanService(
            provider=self._provider,
            max_format_repairs=1,
        ).generate(
            user_input=user_input,
            intent=intent,
            schema=schema,
            committed_memory=committed_memory,
            semantic_model_key=semantic_model_key,
            report_template_key=report_template_key,
            enforce_semantic_grounding=enforce_semantic_grounding,
        )
        return SemanticInterpretationDraft.from_query_plan(
            plan,
            report=intent.intent.value == "report_generation",
        )

    async def interpret_report_sections(
        self,
        user_input: str,
    ) -> SemanticInterpretationDraft:
        candidates = await DeepSeekReportIntentService(
            self._provider,
            max_format_repairs=0,
        ).draft(user_input)
        return SemanticInterpretationDraft(
            mode=SemanticInterpretationMode.REPORT,
            report_section_candidates=candidates,
        )
