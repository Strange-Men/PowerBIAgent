"""Small process-local async primitives for safe runtime metadata reuse.

These helpers deliberately know nothing about semantic plans, query results, or
business facts.  They are used only for short-lived, non-factual metadata.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar, cast


_K = TypeVar("_K", bound=Hashable)
_V = TypeVar("_V")
_I = TypeVar("_I")
_R = TypeVar("_R")


@dataclass(frozen=True)
class _CacheEntry(Generic[_V]):
    value: _V
    expires_at: float


class BoundedTTLCache(Generic[_K, _V]):
    """Deterministic in-memory TTL/LRU cache with a fixed maximum size."""

    def __init__(self, *, max_size: int, ttl_seconds: float) -> None:
        if max_size <= 0:
            raise ValueError("cache max_size must be positive")
        if ttl_seconds <= 0:
            raise ValueError("cache ttl_seconds must be positive")
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[_K, _CacheEntry[_V]] = OrderedDict()

    def get(self, key: _K) -> _V | None:
        now = time.monotonic()
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry.value

    def put(self, key: _K, value: _V) -> None:
        self._entries[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._ttl_seconds,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_size:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()

    def discard_where(self, predicate: Callable[[_K], bool]) -> None:
        for key in tuple(self._entries):
            if predicate(key):
                del self._entries[key]

    def __len__(self) -> int:
        return len(self._entries)


class AsyncSingleFlight(Generic[_K, _V]):
    """Coalesce concurrent identical work without caching its result.

    One waiter cannot cancel work still owned by another waiter.  When the last
    waiter is cancelled, the leader is cancelled too so request-scoped retry or
    metadata work cannot continue without an owner.  The task is removed after
    every success, failure, or cancellation, so a later retry can always become
    a fresh leader.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[_K, asyncio.Task[_V]] = {}
        self._waiters: dict[_K, int] = {}

    async def run(self, key: _K, factory: Callable[[], Awaitable[_V]]) -> _V:
        async with self._lock:
            task = self._tasks.get(key)
            if task is None:
                task = asyncio.create_task(self._run_and_release(key, factory))
                self._tasks[key] = task
            self._waiters[key] = self._waiters.get(key, 0) + 1
        try:
            return await asyncio.shield(task)
        finally:
            leader_to_drain: asyncio.Task[_V] | None = None
            async with self._lock:
                remaining = self._waiters.get(key, 0) - 1
                if remaining > 0:
                    self._waiters[key] = remaining
                else:
                    self._waiters.pop(key, None)
                    if self._tasks.get(key) is task and not task.done():
                        task.cancel()
                        leader_to_drain = task
            if leader_to_drain is not None:
                await asyncio.gather(leader_to_drain, return_exceptions=True)

    async def _run_and_release(
        self,
        key: _K,
        factory: Callable[[], Awaitable[_V]],
    ) -> _V:
        try:
            return await factory()
        finally:
            current = asyncio.current_task()
            async with self._lock:
                if self._tasks.get(key) is current:
                    del self._tasks[key]

    async def clear(self) -> None:
        async with self._lock:
            tasks = tuple(self._tasks.values())
            self._tasks.clear()
            self._waiters.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def bounded_gather_ordered(
    items: Sequence[_I],
    operation: Callable[[_I], Awaitable[_R]],
    *,
    max_concurrency: int,
) -> list[_R]:
    """Run independent work with a hard bound and preserve input order.

    On the first exception or caller cancellation every sibling is cancelled
    and awaited before the original failure is re-raised.  This prevents
    orphan background work while avoiding ``ExceptionGroup`` at callers that
    already own a typed error taxonomy.
    """
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be positive")
    if not items:
        return []
    semaphore = asyncio.Semaphore(min(max_concurrency, len(items)))
    results: list[_R | None] = [None] * len(items)

    async def run_one(index: int, item: _I) -> None:
        async with semaphore:
            results[index] = await operation(item)

    tasks = [
        asyncio.create_task(run_one(index, item))
        for index, item in enumerate(items)
    ]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return [cast(_R, item) for item in results]
