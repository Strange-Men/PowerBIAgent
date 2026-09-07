from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from backend.app.core.performance import (
    PerformanceRecorder,
    bind_performance_recorder,
    current_performance_recorder,
    measure_performance,
    record_performance_retry,
    record_performance_timeout,
    reset_performance_recorder,
)
from backend.app.core.deadline import (
    bind_request_deadline,
    bounded_timeout_seconds,
    remaining_request_seconds,
    reset_request_deadline,
    sleep_with_request_deadline,
)
from backend.app.core.async_runtime import bounded_gather_ordered
from backend.app.harness.errors import ToolTimeoutError
from backend.app.harness.runtime.tool_gateway import (
    ToolExecutionContext,
    ToolGateway,
    ToolSpec,
)
from backend.app.intent.models import IntentType
from backend.app.schemas.data_contracts import UserContext


class _EmptyInput(BaseModel):
    pass


def test_performance_summary_exposes_safe_canonical_measurements() -> None:
    recorder = PerformanceRecorder()
    recorder.record("router", 1.25)
    recorder.record("intent_llm", 2.5)
    recorder.record("persistence", 3.75)
    recorder.record("queue_wait", 4.0, queue_depth=3, worker_id=1)
    recorder.record("schema_read", 5.0, cache="hit")
    recorder.record("mcp_rpc", 6.0, session="reused", worker_id=1)
    recorder.record("llm_task", 7.0)
    record_token = bind_performance_recorder(recorder)
    try:
        record_performance_retry()
        record_performance_timeout()
    finally:
        reset_performance_recorder(record_token)

    summary = recorder.summary()

    assert summary["total_ms"] >= 0
    assert summary["router_ms"] == 1.25
    assert summary["intent_llm_ms"] == 2.5
    assert summary["schema_ms"] == 5.0
    assert summary["queue_wait_ms"] == 4.0
    assert summary["mcp_rpc_ms"] == 6.0
    assert summary["db_ms"] == 3.75
    assert summary["llm_task_ms"] == 7.0
    assert summary["retry_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["cache_hit"] == 1
    assert summary["cache_miss"] == 0
    assert summary["session_new"] == 0
    assert summary["session_reused"] == 1
    assert summary["queue_depth"] == 3
    assert summary["worker_ids"] == [1]
    assert "prompt" not in str(summary).lower()
    assert "connection" not in str(summary).lower()


@pytest.mark.asyncio
async def test_performance_context_isolated_across_concurrent_requests() -> None:
    async def one(operation: str) -> dict[str, object]:
        recorder = PerformanceRecorder()
        token = bind_performance_recorder(recorder)
        try:
            with measure_performance(operation):
                await asyncio.sleep(0)
            assert current_performance_recorder() is recorder
            return recorder.summary()
        finally:
            reset_performance_recorder(token)

    left, right = await asyncio.gather(one("router"), one("grounding"))

    assert left["router_ms"] >= 0
    assert left["grounding_ms"] == 0
    assert right["router_ms"] == 0
    assert right["grounding_ms"] >= 0
    assert current_performance_recorder() is None


@pytest.mark.asyncio
async def test_request_deadline_is_monotonic_inherited_and_reset() -> None:
    token = bind_request_deadline(1.0)
    try:
        parent_remaining = remaining_request_seconds()

        async def read_child_deadline() -> float | None:
            await asyncio.sleep(0)
            return remaining_request_seconds()

        child_remaining = await asyncio.create_task(read_child_deadline())
        assert parent_remaining is not None
        assert child_remaining is not None
        assert 0 < child_remaining <= 1.0
        assert bounded_timeout_seconds(5.0) <= 1.0
    finally:
        reset_request_deadline(token)
    assert remaining_request_seconds() is None


@pytest.mark.asyncio
async def test_retry_sleep_cannot_extend_request_deadline() -> None:
    token = bind_request_deadline(0.01)
    try:
        started = asyncio.get_running_loop().time()
        with pytest.raises(TimeoutError):
            await sleep_with_request_deadline(1.0)
        assert asyncio.get_running_loop().time() - started < 0.2
    finally:
        reset_request_deadline(token)


@pytest.mark.asyncio
async def test_tool_gateway_does_not_retry_expired_request_deadline() -> None:
    attempts = 0

    async def handler(_: _EmptyInput) -> _EmptyInput:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(1)
        return _EmptyInput()

    gateway = ToolGateway()
    gateway.register(ToolSpec(
        name="deadline_fixture",
        input_model=_EmptyInput,
        output_model=_EmptyInput,
        timeout_seconds=1,
        max_retries=3,
        allowed_intents=[IntentType.DATA_QUESTION],
        handler=handler,
    ))
    recorder = PerformanceRecorder()
    performance_token = bind_performance_recorder(recorder)
    deadline_token = bind_request_deadline(0.01)
    try:
        with pytest.raises(ToolTimeoutError, match="request deadline"):
            await gateway.execute(
                "deadline_fixture",
                ToolExecutionContext(
                    intent=IntentType.DATA_QUESTION,
                    user=UserContext(allowed_tools=["deadline_fixture"]),
                ),
                _EmptyInput(),
            )
    finally:
        reset_request_deadline(deadline_token)
        reset_performance_recorder(performance_token)
    assert attempts == 1
    assert recorder.summary()["retry_count"] == 0
    assert recorder.summary()["timeout_count"] == 1


@pytest.mark.asyncio
async def test_bounded_gather_preserves_order_and_concurrency_limit() -> None:
    active = 0
    maximum = 0

    async def operation(value: int) -> int:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep((5 - value) * 0.001)
            return value * 10
        finally:
            active -= 1

    results = await bounded_gather_ordered(
        [1, 2, 3, 4], operation, max_concurrency=2
    )
    assert results == [10, 20, 30, 40]
    assert maximum == 2


@pytest.mark.asyncio
async def test_bounded_gather_cancels_and_awaits_siblings_on_failure() -> None:
    cancelled = asyncio.Event()

    async def operation(value: int) -> int:
        if value == 1:
            await asyncio.sleep(0)
            raise RuntimeError("fixture_failure")
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return value

    with pytest.raises(RuntimeError, match="fixture_failure"):
        await bounded_gather_ordered([0, 1, 2], operation, max_concurrency=3)
    assert cancelled.is_set()
