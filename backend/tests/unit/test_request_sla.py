"""M5.10.6 end-to-end SLA separation and deadline cleanup regressions."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from pydantic import BaseModel

from backend.app.application.turn_pipeline import TurnPipeline
from backend.app.core.deadline import bind_request_deadline, reset_request_deadline
from backend.app.harness.errors import ToolTimeoutError
from backend.app.harness.models import HarnessConfig
from backend.app.harness.runtime.tool_gateway import (
    ToolExecutionContext,
    ToolGateway,
    ToolSpec,
)
from backend.app.intent.models import IntentType
from backend.app.intent.semantic_interpreter import (
    SemanticFrame,
    SemanticInterpretationMode,
)
from backend.app.llm.base import LLMRequest, LLMTimeoutError
from backend.app.llm.openai_compatible import OpenAICompatibleLLMProvider
from backend.app.llm.profiles import (
    LLMCapabilityFlags,
    LLMModelProfile,
    LLMProviderProtocol,
)
from backend.app.memory.models import RuntimeDataMode
from backend.app.memory.repository import InMemoryMemoryRepository
from backend.app.schemas.data_contracts import QueryShape
from backend.app.schemas.data_contracts import UserContext


class _StructuredResult(BaseModel):
    status: str


class _EmptyInput(BaseModel):
    pass


class _EmptyOutput(BaseModel):
    ok: bool


async def _understand_as_scalar(**_: object) -> dict[str, object]:
    return {
        "_semantic_frame": SemanticFrame(
            mode=SemanticInterpretationMode.DATA,
            query_shape=QueryShape.SCALAR,
            measure_mentions=("销售额",),
            evidence_spans=(
                {"slot": "query_shape", "text": "销售额"},
                {"slot": "measure", "text": "销售额"},
            ),
        )
    }


async def _execute_pipeline(
    pipeline: TurnPipeline,
    callback: object,
    *,
    request_id: str,
) -> dict[str, object]:
    return await pipeline.execute(
        message="销售额是多少",
        conversation_id="sla-conversation",
        request_id=request_id,
        semantic_model_key="test_model",
        report_template_key=None,
        runtime_mode=RuntimeDataMode.MOCK,
        is_mock=True,
        llm_provider_name="mock",
        powerbi_provider_name="mock_powerbi",
        do_conversation=_understand_as_scalar,
        do_execute=callback,
    )


@pytest.mark.asyncio
async def test_legal_multistage_work_can_finish_after_old_sla_before_new_sla() -> None:
    """Scaled clock: 0.12s represents old 120s and 0.18s the new 180s."""
    config = HarnessConfig.model_construct(request_timeout_seconds=0.18)
    pipeline = TurnPipeline(config=config, memory_repo=InMemoryMemoryRepository())

    async def legal_slow_turn(**kwargs: object) -> dict[str, object]:
        await asyncio.sleep(0.13)
        return {
            "request_id": kwargs["effective_req_id"],
            "conversation_id": kwargs["effective_conv_id"],
            "terminal_state": "completed",
            "response_type": "answer",
            "answer": "verified",
            "memory_commit": False,
            "is_mock": True,
            "source_mode": "mock",
            "allowed_tools": [],
        }

    started = time.perf_counter()
    result = await _execute_pipeline(
        pipeline,
        legal_slow_turn,
        request_id="sla-completes-before-180",
    )
    elapsed = time.perf_counter() - started

    assert elapsed >= 0.12
    assert elapsed < 0.18
    assert result["terminal_state"] == "completed"


@pytest.mark.asyncio
async def test_overall_deadline_cancels_turn_without_memory_or_snapshot() -> None:
    """A request beyond the overall SLA is cancelled and leaves no partial state."""
    config = HarnessConfig.model_construct(request_timeout_seconds=0.04)
    memory = InMemoryMemoryRepository()
    pipeline = TurnPipeline(config=config, memory_repo=memory)
    cancelled = asyncio.Event()

    async def over_sla_turn(**_: object) -> dict[str, object]:
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()
        raise AssertionError("unreachable")

    with pytest.raises(TimeoutError):
        await _execute_pipeline(
            pipeline,
            over_sla_turn,
            request_id="sla-controlled-timeout",
        )

    assert cancelled.is_set()
    assert (
        await memory.get_by_request_id(
            "sla-controlled-timeout", RuntimeDataMode.MOCK
        )
        is None
    )
    assert (
        await pipeline.snapshot_store.get(
            "sla-controlled-timeout", RuntimeDataMode.MOCK
        )
        is None
    )


@pytest.mark.asyncio
async def test_single_provider_call_still_obeys_its_shorter_child_timeout() -> None:
    async def slow_handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    profile = LLMModelProfile(
        profile_key="deepseek",
        display_name="DeepSeek",
        provider_protocol=LLMProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        base_url="https://api.example.test/v1",
        model="deepseek-chat",
        timeout_seconds=0.02,
        capabilities=LLMCapabilityFlags(json_object_response=True),
    )
    provider = OpenAICompatibleLLMProvider(
        profile=profile,
        api_key="unit-secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(slow_handler)),
        max_attempts=1,
    )
    deadline_token = bind_request_deadline(0.2)
    started = time.perf_counter()
    try:
        with pytest.raises(LLMTimeoutError):
            await provider.generate(
                LLMRequest(messages=[{"role": "user", "content": "JSON"}]),
                _StructuredResult,
            )
    finally:
        reset_request_deadline(deadline_token)
        await provider.aclose()

    assert time.perf_counter() - started < 0.1


@pytest.mark.asyncio
async def test_availability_probe_cannot_outlive_overall_deadline_or_retry() -> None:
    gateway = ToolGateway()
    attempts = 0

    async def slow_probe(_: _EmptyInput) -> _EmptyOutput:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(1)
        return _EmptyOutput(ok=True)

    gateway.register(
        ToolSpec(
            name="availability_probe",
            input_model=_EmptyInput,
            output_model=_EmptyOutput,
            timeout_seconds=1,
            max_retries=1,
            allowed_intents=[IntentType.DATA_QUESTION],
            handler=slow_probe,
        )
    )
    deadline_token = bind_request_deadline(0.03)
    try:
        with pytest.raises(ToolTimeoutError, match="request deadline"):
            await gateway.execute(
                "availability_probe",
                ToolExecutionContext(
                    intent=IntentType.DATA_QUESTION,
                    user=UserContext(allowed_tools=["availability_probe"]),
                ),
                _EmptyInput(),
            )
    finally:
        reset_request_deadline(deadline_token)

    assert attempts == 1
