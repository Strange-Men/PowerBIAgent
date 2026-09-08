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
async def test_cancelled_queue_items_never_leak_raw_queue_full(fake_stdio) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=3,
        admission_timeout_seconds=0.02,
    )
    blocking_started = asyncio.Event()
    release_blocking = asyncio.Event()
    replacement_executed = asyncio.Event()
    cancelled_executions = 0

    async def blocking(*_: object) -> None:
        blocking_started.set()
        await release_blocking.wait()

    async def cancelled_queued(*_: object) -> None:
        nonlocal cancelled_executions
        cancelled_executions += 1

    async def replacement(*_: object) -> str:
        replacement_executed.set()
        return "replacement"

    first = asyncio.create_task(client._run_session(blocking))
    await asyncio.wait_for(blocking_started.wait(), timeout=1.0)
    cancelled = [
        asyncio.create_task(client._run_session(cancelled_queued))
        for _ in range(2)
    ]
    while client._work_queue.qsize() < 2:
        await asyncio.sleep(0)
    for task in cancelled:
        task.cancel()
    await asyncio.gather(*cancelled, return_exceptions=True)

    replacement_task = asyncio.create_task(client._run_session(replacement))
    controlled_error: LocalMCPConnectionError | None = None
    raw_error: BaseException | None = None
    try:
        observation_deadline = asyncio.get_running_loop().time() + 0.2
        while (
            client._work_queue.qsize() < 3
            and not replacement_task.done()
            and asyncio.get_running_loop().time() < observation_deadline
        ):
            await asyncio.sleep(0)
        if client._work_queue.qsize() == 3:
            try:
                await client._run_session(lambda *_: asyncio.sleep(0))
            except LocalMCPConnectionError as exc:
                controlled_error = exc
            except BaseException as exc:
                raw_error = exc
        else:
            try:
                await replacement_task
            except LocalMCPConnectionError as exc:
                controlled_error = exc
            except BaseException as exc:
                raw_error = exc
    finally:
        release_blocking.set()
        await asyncio.wait_for(first, timeout=1.0)
        if not replacement_task.done():
            await asyncio.wait_for(replacement_task, timeout=1.0)
        await asyncio.wait_for(client.aclose(), timeout=1.0)

    assert raw_error is None
    assert controlled_error is not None
    assert controlled_error.error_type == "local_mcp_overloaded"
    assert cancelled_executions == 0
    assert replacement_executed.is_set() is False
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 3
    assert client.lifecycle_snapshot()["session_residual"] == 0


@pytest.mark.asyncio
async def test_inflight_cancellation_keeps_per_request_capacity_until_drain(
    fake_stdio,
) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=2,
        max_pending_operations=2,
        max_operations_per_request=1,
        admission_timeout_seconds=1,
    )
    recorder = PerformanceRecorder()
    token = bind_performance_recorder(recorder)
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()
    active_handlers = 0
    max_active_handlers = 0

    async def first_operation(*_: object) -> None:
        nonlocal active_handlers, max_active_handlers
        active_handlers += 1
        max_active_handlers = max(max_active_handlers, active_handlers)
        first_started.set()
        try:
            await release_first.wait()
        finally:
            active_handlers -= 1

    async def second_operation(*_: object) -> str:
        nonlocal active_handlers, max_active_handlers
        active_handlers += 1
        max_active_handlers = max(max_active_handlers, active_handlers)
        second_started.set()
        try:
            return "second"
        finally:
            active_handlers -= 1

    first = asyncio.create_task(client._run_session(first_operation))
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    second = asyncio.create_task(client._run_session(second_operation))
    started_before_drain = False
    try:
        await asyncio.wait_for(second_started.wait(), timeout=0.05)
        started_before_drain = True
    except TimeoutError:
        pass
    finally:
        release_first.set()
        assert await asyncio.wait_for(second, timeout=1.0) == "second"
        reset_performance_recorder(token)
        await asyncio.wait_for(client.aclose(), timeout=1.0)

    assert started_before_drain is False
    assert max_active_handlers == 1
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 2
    assert client.lifecycle_snapshot()["session_residual"] == 0


@pytest.mark.asyncio
async def test_queued_cancellation_then_shutdown_drains_without_residual(
    fake_stdio,
) -> None:
    sessions, closed = fake_stdio
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=2,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    queued_executions = 0

    async def blocking(*_: object) -> str:
        started.set()
        await release.wait()
        return "completed"

    async def queued(*_: object) -> None:
        nonlocal queued_executions
        queued_executions += 1

    first = asyncio.create_task(client._run_session(blocking))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    cancelled = asyncio.create_task(client._run_session(queued))
    while client._work_queue.qsize() < 1:
        await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    shutdown = asyncio.create_task(client.aclose())
    await asyncio.sleep(0)
    assert shutdown.done() is False
    assert client._operation_slots._value == 0
    release.set()

    assert await asyncio.wait_for(first, timeout=1.0) == "completed"
    await asyncio.wait_for(shutdown, timeout=1.0)
    assert queued_executions == 0
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 2
    assert len(sessions) == len(closed)
    assert client.lifecycle_snapshot()["active_workers"] == 0


@pytest.mark.asyncio
async def test_inflight_cancellation_then_shutdown_keeps_capacity_until_drain(
    fake_stdio,
) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=1,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking(*_: object) -> None:
        started.set()
        await release.wait()

    request = asyncio.create_task(client._run_session(blocking))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request

    shutdown = asyncio.create_task(client.aclose())
    await asyncio.sleep(0)
    assert shutdown.done() is False
    assert client._operation_slots._value == 0
    release.set()
    await asyncio.wait_for(shutdown, timeout=1.0)

    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 1
    assert client.lifecycle_snapshot()["session_residual"] == 0


@pytest.mark.asyncio
async def test_worker_transport_crash_recovers_queued_work_during_shutdown(
    fake_stdio,
) -> None:
    sessions, closed = fake_stdio
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=2,
    )
    crash_started = asyncio.Event()
    release_crash = asyncio.Event()

    class BrokenResourceError(Exception):
        pass

    async def crash(*_: object) -> None:
        crash_started.set()
        await release_crash.wait()
        raise BrokenResourceError()

    crashing = asyncio.create_task(client._run_session(crash))
    await asyncio.wait_for(crash_started.wait(), timeout=1.0)
    queued = asyncio.create_task(
        client._run_session(lambda *_: asyncio.sleep(0, result="recovered"))
    )
    while client._work_queue.qsize() < 1:
        await asyncio.sleep(0)
    shutdown = asyncio.create_task(client.aclose())
    await asyncio.sleep(0)
    release_crash.set()

    with pytest.raises(LocalMCPConnectionError):
        await asyncio.wait_for(crashing, timeout=1.0)
    assert await asyncio.wait_for(queued, timeout=1.0) == "recovered"
    await asyncio.wait_for(shutdown, timeout=1.0)

    assert len(sessions) == 2
    assert len(closed) == 2
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 2
    assert client.lifecycle_snapshot()["active_workers"] == 0


@pytest.mark.asyncio
async def test_worker_transport_crash_skips_cancelled_queued_work(fake_stdio) -> None:
    sessions, closed = fake_stdio
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=2,
    )
    crash_started = asyncio.Event()
    release_crash = asyncio.Event()
    cancelled_executions = 0

    class BrokenResourceError(Exception):
        pass

    async def crash(*_: object) -> None:
        crash_started.set()
        await release_crash.wait()
        raise BrokenResourceError()

    async def cancelled_queued(*_: object) -> None:
        nonlocal cancelled_executions
        cancelled_executions += 1

    crashing = asyncio.create_task(client._run_session(crash))
    await asyncio.wait_for(crash_started.wait(), timeout=1.0)
    cancelled = asyncio.create_task(client._run_session(cancelled_queued))
    while client._work_queue.qsize() < 1:
        await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release_crash.set()
    with pytest.raises(LocalMCPConnectionError):
        await asyncio.wait_for(crashing, timeout=1.0)
    await asyncio.wait_for(client.aclose(), timeout=1.0)

    assert cancelled_executions == 0
    assert len(sessions) == len(closed)
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 2
    assert client.lifecycle_snapshot()["active_workers"] == 0


@pytest.mark.asyncio
async def test_worker_restart_honors_expired_queued_request_deadline(
    fake_stdio,
) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=2,
    )
    crash_started = asyncio.Event()
    release_crash = asyncio.Event()

    class BrokenResourceError(Exception):
        pass

    async def crash(*_: object) -> None:
        crash_started.set()
        await release_crash.wait()
        raise BrokenResourceError()

    crashing = asyncio.create_task(client._run_session(crash))
    await asyncio.wait_for(crash_started.wait(), timeout=1.0)
    deadline_token = bind_request_deadline(0.02)
    try:
        expired = asyncio.create_task(
            client._run_session(lambda *_: asyncio.Event().wait())
        )
    finally:
        reset_request_deadline(deadline_token)
    while client._work_queue.qsize() < 1:
        await asyncio.sleep(0)
    await asyncio.sleep(0.03)
    release_crash.set()

    with pytest.raises(LocalMCPConnectionError):
        await asyncio.wait_for(crashing, timeout=1.0)
    with pytest.raises(LocalMCPConnectionError) as exc_info:
        await asyncio.wait_for(expired, timeout=1.0)
    assert exc_info.value.error_type == "request_deadline_exceeded"
    assert exc_info.value.retryable is False
    await asyncio.wait_for(client.aclose(), timeout=1.0)

    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 2
    assert client.lifecycle_snapshot()["session_residual"] == 0


@pytest.mark.asyncio
async def test_repeated_aclose_is_idempotent_after_worker_session(fake_stdio) -> None:
    sessions, closed = fake_stdio
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=1,
    )

    assert await client._run_session(
        lambda *_: asyncio.sleep(0, result="completed")
    ) == "completed"
    await asyncio.wait_for(client.aclose(), timeout=1.0)
    first_snapshot = client.lifecycle_snapshot()
    await asyncio.wait_for(client.aclose(), timeout=1.0)

    assert len(sessions) == 1
    assert len(closed) == 1
    assert client.lifecycle_snapshot() == first_snapshot
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 1


@pytest.mark.asyncio
async def test_cancelled_admission_waiter_does_not_bypass_request_fairness(
    fake_stdio,
) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=2,
        max_operations_per_request=1,
        admission_timeout_seconds=1,
    )
    recorder = PerformanceRecorder()
    token = bind_performance_recorder(recorder)
    first_started = asyncio.Event()
    third_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first_operation(*_: object) -> None:
        first_started.set()
        await release_first.wait()

    async def third_operation(*_: object) -> str:
        third_started.set()
        return "third"

    first = asyncio.create_task(client._run_session(first_operation))
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    cancelled_waiter = asyncio.create_task(
        client._run_session(lambda *_: asyncio.sleep(0))
    )
    await asyncio.sleep(0)
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter

    third = asyncio.create_task(client._run_session(third_operation))
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(third_started.wait(), timeout=0.05)
        release_first.set()
        await asyncio.wait_for(first, timeout=1.0)
        assert await asyncio.wait_for(third, timeout=1.0) == "third"
    finally:
        reset_performance_recorder(token)
        await asyncio.wait_for(client.aclose(), timeout=1.0)

    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 2
    assert client.lifecycle_snapshot()["session_residual"] == 0


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


@pytest.mark.asyncio
async def test_shutdown_rejects_request_paused_before_enqueue_without_orphan(
    fake_stdio,
) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=1,
    )
    workers_ready = asyncio.Event()
    allow_enqueue = asyncio.Event()
    original_ensure_workers = client._ensure_workers

    async def ensure_workers_then_pause() -> None:
        await original_ensure_workers()
        workers_ready.set()
        await allow_enqueue.wait()

    client._ensure_workers = ensure_workers_then_pause  # type: ignore[method-assign]
    request = asyncio.create_task(
        client._run_session(lambda *_: asyncio.sleep(0, result="unexpected"))
    )
    await asyncio.wait_for(workers_ready.wait(), timeout=1.0)

    await asyncio.wait_for(client.aclose(), timeout=1.0)
    allow_enqueue.set()

    with pytest.raises(LocalMCPConnectionError) as exc_info:
        await asyncio.wait_for(request, timeout=1.0)

    assert exc_info.value.error_type == "local_mcp_client_closed"
    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 1
    assert client.lifecycle_snapshot() == {
        "worker_count": 1,
        "sessions_started": 0,
        "sessions_closed": 0,
        "session_residual": 0,
        "active_workers": 0,
    }


@pytest.mark.asyncio
async def test_shutdown_drains_already_accepted_work(fake_stdio) -> None:
    client = PowerBILocalMCPClient(
        timeout_seconds=2,
        worker_count=1,
        max_pending_operations=1,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def accepted(*_: object) -> str:
        started.set()
        await release.wait()
        return "completed"

    request = asyncio.create_task(client._run_session(accepted))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    shutdown = asyncio.create_task(client.aclose())
    await asyncio.sleep(0)

    assert shutdown.done() is False
    release.set()
    assert await asyncio.wait_for(request, timeout=1.0) == "completed"
    await asyncio.wait_for(shutdown, timeout=1.0)

    assert client._work_queue.qsize() == 0
    assert client._operation_slots._value == 1
    lifecycle = client.lifecycle_snapshot()
    assert lifecycle["active_workers"] == 0
    assert lifecycle["session_residual"] == 0
