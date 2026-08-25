"""M5.5 request-local performance diagnostics stay bounded and numeric."""

import asyncio

import pytest

from backend.app.harness.observability.phase_timing import (
    PHASE_NAMES,
    PhaseTimingCollector,
    bind_phase_timings,
    reset_phase_timings,
    timed_phase,
)


@timed_phase("mcp_enumerate/connect")
async def _fake_connect() -> str:
    await asyncio.sleep(0)
    return "connected"


@pytest.mark.asyncio
async def test_phase_timing_has_complete_safe_shape() -> None:
    collector = PhaseTimingCollector()
    token = bind_phase_timings(collector)
    try:
        with collector.measure("intent_llm"):
            await asyncio.sleep(0)
        assert await _fake_connect() == "connected"
    finally:
        reset_phase_timings(token)

    timings = collector.finish()
    assert tuple(timings) == PHASE_NAMES
    assert timings["intent_llm"] >= 0
    assert timings["mcp_enumerate/connect"] >= 0
    assert timings["total"] >= timings["intent_llm"]
    assert all(isinstance(value, float) and value >= 0 for value in timings.values())
    serialized = repr(timings).casefold()
    assert "prompt" not in serialized
    assert "response" not in serialized
    assert "secret" not in serialized
