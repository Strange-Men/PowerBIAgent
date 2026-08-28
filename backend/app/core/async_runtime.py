"""Small process-local async primitives for safe runtime metadata reuse.

These helpers deliberately know nothing about semantic plans, query results, or
business facts.  They are used only for short-lived, non-factual metadata.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar


_K = TypeVar("_K", bound=Hashable)
_V = TypeVar("_V")


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

    Waiter cancellation is shielded from the shared leader task.  The task is
    removed after every success, failure, or cancellation, so a later retry can
    always become a fresh leader.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[_K, asyncio.Task[_V]] = {}

    async def run(self, key: _K, factory: Callable[[], Awaitable[_V]]) -> _V:
        async with self._lock:
            task = self._tasks.get(key)
            if task is None:
                task = asyncio.create_task(self._run_and_release(key, factory))
                self._tasks[key] = task
        return await asyncio.shield(task)

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
            self._tasks.clear()
