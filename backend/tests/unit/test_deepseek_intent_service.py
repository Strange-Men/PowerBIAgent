"""Regression tests for the single LLM Understanding authority.

The former ``DeepSeekIntentService`` was removed in M5.10.6 because it was a
second open-language authority. These tests retain its safety/repair coverage
at the replacement ``LLMSemanticInterpreter`` boundary.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.intent.models import TurnRelation
from backend.app.intent.semantic_interpreter import (
    LLMSemanticInterpreter,
    SemanticCoverageDecision,
    SemanticEvidenceSpan,
    SemanticFrame,
    SemanticInterpretationError,
    SemanticInterpretationMode,
)
from backend.app.llm.base import (
    LLMErrorCategory,
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTask,
)
from backend.app.schemas.data_contracts import QueryShape


def _general(answer: str = "可以，我们聊聊。") -> SemanticFrame:
    return SemanticFrame(
        mode=SemanticInterpretationMode.GENERAL,
        general_answer=answer,
    )


def _scalar() -> SemanticFrame:
    return SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("销售额",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="销售额"),
            SemanticEvidenceSpan(slot="measure", text="销售额"),
        ),
    )


class _QueueProvider(LLMProvider):
    provider_name = "test-understanding"
    is_mock = False

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls: list[tuple[LLMRequest, type]] = []

    async def generate(self, request: LLMRequest, output_type: type) -> LLMResponse:
        self.calls.append((request, output_type))
        if not self.items:
            raise AssertionError("unexpected extra understanding call")
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return LLMResponse(content="{}", structured=item, model="offline")


def _accept() -> SemanticCoverageDecision:
    return SemanticCoverageDecision(decision="ACCEPT")


@pytest.mark.asyncio
async def test_general_is_one_current_message_only_understanding_call() -> None:
    provider = _QueueProvider(_general())

    frame = await LLMSemanticInterpreter(provider).interpret("我今天有点累，聊两句")

    assert frame.mode is SemanticInterpretationMode.GENERAL
    assert frame.general_answer
    assert [request.task for request, _ in provider.calls] == [LLMTask.UNDERSTANDING]
    prompt = provider.calls[0][0].messages[-1]["content"]
    assert "我今天有点累，聊两句" in prompt
    assert "DAX" not in frame.model_dump_json()


@pytest.mark.asyncio
async def test_data_uses_understanding_then_veto_only_coverage() -> None:
    provider = _QueueProvider(_scalar(), _accept())

    frame = await LLMSemanticInterpreter(provider).interpret("今年销售额")

    assert frame.query_shape is QueryShape.SCALAR
    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]
    assert provider.calls[1][1] is SemanticCoverageDecision


@pytest.mark.asyncio
async def test_report_mode_is_forced_without_creating_template_authority() -> None:
    provider = _QueueProvider(
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=None,
            unresolved_mentions=("销售",),
            evidence_spans=(SemanticEvidenceSpan(slot="unresolved", text="销售"),),
        ),
        _accept(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret(
        "生成销售报表",
        forced_mode=SemanticInterpretationMode.REPORT,
    )

    assert frame.mode is SemanticInterpretationMode.REPORT
    assert frame.output_mode == "report"
    assert "requested_template" not in type(frame).model_fields


@pytest.mark.asyncio
async def test_follow_up_relation_and_changed_slots_are_language_only() -> None:
    provider = _QueueProvider(
        SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            relation=TurnRelation.FOLLOW_UP,
            query_shape=None,
            measure_mentions=("销售额",),
            changed_slots=("measure",),
            referenced_context_slots=("query_shape", "dimension", "top_n", "sort"),
            evidence_spans=(SemanticEvidenceSpan(slot="measure", text="销售额"),),
        ),
        _accept(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret("按销售额")

    assert frame.relation is TurnRelation.FOLLOW_UP
    assert frame.changed_slots == ("measure",)
    assert frame.query_shape is None


@pytest.mark.asyncio
async def test_non_verbatim_semantic_evidence_fails_closed_after_one_repair() -> None:
    invalid = SemanticFrame(
        mode=SemanticInterpretationMode.DATA,
        query_shape=QueryShape.SCALAR,
        measure_mentions=("revenue",),
        evidence_spans=(
            SemanticEvidenceSpan(slot="query_shape", text="revenue"),
            SemanticEvidenceSpan(slot="measure", text="revenue"),
        ),
    )
    provider = _QueueProvider(invalid, invalid)

    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret("销售额是多少")

    assert len(provider.calls) == 2
    assert all(call.task is LLMTask.UNDERSTANDING for call, _ in provider.calls)


@pytest.mark.asyncio
async def test_coverage_omission_vetoes_and_repairs_at_most_once() -> None:
    missing = SemanticCoverageDecision(
        decision="MISSING_SEMANTIC_SPAN",
        missing_span="华南",
    )
    provider = _QueueProvider(_scalar(), missing, _scalar(), missing)

    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret("华南今年销售额")

    assert [request.task for request, _ in provider.calls] == [
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
        LLMTask.UNDERSTANDING,
        LLMTask.UNDERSTANDING_COVERAGE,
    ]


@pytest.mark.asyncio
async def test_non_retryable_provider_failure_is_not_retried() -> None:
    provider = _QueueProvider(
        LLMProviderError(
            "secret response must not escape",
            provider="offline",
            retryable=False,
            error_category=LLMErrorCategory.AUTHENTICATION,
        )
    )

    with pytest.raises(SemanticInterpretationError) as captured:
        await LLMSemanticInterpreter(provider).interpret("销售额")

    assert len(provider.calls) == 1
    assert "secret response" not in str(captured.value)


@pytest.mark.asyncio
async def test_retryable_provider_failure_gets_one_bounded_repair() -> None:
    provider = _QueueProvider(
        LLMProviderError(
            "temporary",
            provider="offline",
            retryable=True,
            error_category=LLMErrorCategory.RESPONSE_VALIDATION,
        ),
        _general(),
    )

    frame = await LLMSemanticInterpreter(provider).interpret("聊两句")

    assert frame.mode is SemanticInterpretationMode.GENERAL
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_blank_input_and_mock_provider_are_rejected() -> None:
    provider = _QueueProvider(_general())
    with pytest.raises(SemanticInterpretationError):
        await LLMSemanticInterpreter(provider).interpret("   ")

    provider.is_mock = True
    with pytest.raises(SemanticInterpretationError):
        LLMSemanticInterpreter(provider)


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "general", "general_answer": ""},
        {"mode": "general", "general_answer": "ok", "measure_mentions": ["x"]},
        {"mode": "data", "general_answer": "invented fact"},
        {"mode": "report", "output_mode": "answer", "unresolved_mentions": ["x"]},
        {"mode": "data", "query_shape": "ninth_shape"},
    ],
)
def test_semantic_frame_strict_cross_field_contract(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SemanticFrame.model_validate(payload)


def test_semantic_frame_forbids_canonical_execution_and_fact_fields() -> None:
    with pytest.raises(ValidationError):
        SemanticFrame.model_validate({
            "mode": "data",
            "query_shape": "scalar",
            "canonical_object_id": "measure:Sales:TotalSales",
            "dax": "EVALUATE ...",
            "numeric_answer": 123,
        })
