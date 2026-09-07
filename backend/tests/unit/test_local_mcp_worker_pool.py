from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from backend.app.powerbi import local_mcp as local_mcp_module
from backend.app.powerbi.local_mcp import (
    LocalMCPConnectionError,
    LocalMCPErrorCategory,
    PowerBILocalMCPClient,
)
from backend.app.core.performance import (
    PerformanceRecorder,
    bind_performance_recorder,
    reset_performance_recorder,
)
from backend.app.core.deadline import bind_request_deadline, reset_request_deadline


@pytest.fixture
def fake_stdio(monkeypatch):
    sessions: list[object] = []
    closed: list[object] = []

    class FakePersistentClient:
        protocol_version = "offline-fixture"

        def __init__(self, *_: object, **__: object) -> None:
            sessions.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            closed.append(self)

        async def list_tools(self, *, cursor=None):
            return SimpleNamespace(tools=[], next_cursor=None)

    monkeypatch.setattr(local_mcp_module.shutil, "which", lambda _: "fixture")
    monkeypatch.setattr(local_mcp_module, "stdio_client", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(local_mcp_module, "Client", FakePersistentClient)
    return sessions, closed


@pytest.mark.asyncio
async def test_four_workers_execute_independent_operations_concurrently(fake_stdio) -> None:
    sessions, closed = fake_stdio
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=4,
        max_pending_operations=8,
    )

    async def operation(*_: object) -> int:
        await asyncio.sleep(0.05)
        return 1

    started = time.perf_counter()
    results = await asyncio.gather(*(client._run_session(operation) for _ in range(4)))
    wall = time.perf_counter() - started

    assert results == [1, 1, 1, 1]
    assert wall < 0.16
    assert len(sessions) == 4
    assert client.session_generation == 4
    await client.aclose()
    assert len(closed) == 4
    assert client.lifecycle_snapshot() == {
        "worker_count": 4,
        "sessions_started": 4,
        "sessions_closed": 4,
        "session_residual": 0,
        "active_workers": 0,
    }


@pytest.mark.asyncio
async def test_admission_is_bounded_and_overload_fails_fast(fake_stdio) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=1,
        admission_timeout_seconds=0.02,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(*_: object) -> None:
        started.set()
        await release.wait()

    first = asyncio.create_task(client._run_session(slow))
    await started.wait()
    with pytest.raises(LocalMCPConnectionError) as exc_info:
        await client._run_session(lambda *_: asyncio.sleep(0))
    assert exc_info.value.category == LocalMCPErrorCategory.MCP_TIMEOUT
    assert exc_info.value.error_type == "local_mcp_overloaded"
    release.set()
    await first
    await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_queued_work_never_executes(fake_stdio) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=3,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    executed: list[str] = []

    async def blocking(*_: object) -> None:
        started.set()
        await release.wait()

    async def queued(*_: object) -> None:
        executed.append("queued")

    first = asyncio.create_task(client._run_session(blocking))
    await started.wait()
    cancelled = asyncio.create_task(client._run_session(queued))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()
    await first
    await asyncio.sleep(0)

    assert executed == []
    await client.aclose()


@pytest.mark.asyncio
async def test_one_worker_failure_does_not_stop_other_workers(fake_stdio) -> None:
    sessions, _ = fake_stdio
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=2,
        max_pending_operations=4,
    )

    class BrokenResourceError(Exception):
        pass

    async def crash(*_: object) -> None:
        raise BrokenResourceError()

    async def healthy(*_: object) -> str:
        await asyncio.sleep(0.02)
        return "healthy"

    failed, succeeded = await asyncio.gather(
        client._run_session(crash),
        client._run_session(healthy),
        return_exceptions=True,
    )
    assert isinstance(failed, LocalMCPConnectionError)
    assert succeeded == "healthy"

    recovered = await client._run_session(healthy)
    assert recovered == "healthy"
    assert len(sessions) >= 2
    await client.aclose()
    lifecycle = client.lifecycle_snapshot()
    assert lifecycle["sessions_started"] == lifecycle["sessions_closed"]
    assert lifecycle["session_residual"] == 0
    assert lifecycle["active_workers"] == 0


@pytest.mark.asyncio
async def test_per_request_admission_prevents_one_request_monopolizing_pool(fake_stdio) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=4,
        max_pending_operations=8,
        max_operations_per_request=1,
        admission_timeout_seconds=1,
    )
    recorder = PerformanceRecorder()
    token = bind_performance_recorder(recorder)
    try:
        async def operation(*_: object) -> None:
            await asyncio.sleep(0.03)

        started = time.perf_counter()
        await asyncio.gather(*(client._run_session(operation) for _ in range(4)))
        wall = time.perf_counter() - started
    finally:
        reset_performance_recorder(token)

    assert wall >= 0.10
    assert recorder.summary()["worker_ids"]
    await client.aclose()


@pytest.mark.asyncio
async def test_worker_rebinds_each_request_deadline_without_context_bleed(fake_stdio) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=2,
    )

    first_token = bind_request_deadline(0.02)
    try:
        with pytest.raises(LocalMCPConnectionError) as exc_info:
            await client._run_session(lambda *_: asyncio.sleep(0.05))
        assert exc_info.value.category == LocalMCPErrorCategory.MCP_TIMEOUT
        assert exc_info.value.error_type == "request_deadline_exceeded"
        assert exc_info.value.retryable is False
    finally:
        reset_request_deadline(first_token)

    second_token = bind_request_deadline(1.0)
    try:
        result = await client._run_session(
            lambda *_: asyncio.sleep(0.01, result="second")
        )
    finally:
        reset_request_deadline(second_token)

    assert result == "second"
    await client.aclose()
