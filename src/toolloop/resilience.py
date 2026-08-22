"""Composable provider wrappers for production resilience."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence

from ._types import Message


class _RateLimited:
    """Wraps a provider with a concurrency cap and/or a minimum call interval."""

    def __init__(self, provider, concurrency: int | None, min_interval: float | None):
        self._provider = provider
        self._semaphore = asyncio.Semaphore(concurrency) if concurrency else None
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def _acquire(self) -> None:
        if self._semaphore is not None:
            await self._semaphore.acquire()
        if self._min_interval is not None:
            # spacing is serialized; the semaphore slot (if any) is held while waiting
            async with self._lock:
                elapsed = time.monotonic() - self._last_call
                if elapsed < self._min_interval:
                    await asyncio.sleep(self._min_interval - elapsed)
                self._last_call = time.monotonic()

    def _release(self) -> None:
        if self._semaphore is not None:
            self._semaphore.release()

    async def complete(self, messages: Sequence[Message]) -> str:
        await self._acquire()
        try:
            return await self._provider.complete(messages)
        finally:
            self._release()


class _RateLimitedStreaming(_RateLimited):
    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        await self._acquire()
        try:
            async for delta in self._provider.stream(messages):
                yield delta
        finally:
            self._release()


def rate_limited(provider, *, concurrency: int | None = None, min_interval: float | None = None):
    """Wrap a provider with a concurrency cap and/or a minimum interval between calls.

    Share one wrapped provider across agents for a process-wide limit. Falls
    back gracefully: no options means plain pass-through. ``stream`` and
    ``last_usage`` are forwarded when the inner provider has them.
    """
    if concurrency is None and min_interval is None:
        return provider
    base = _RateLimitedStreaming if hasattr(provider, "stream") else _RateLimited
    wrapper = base(provider, concurrency, min_interval)
    if hasattr(provider, "last_usage"):
        wrapper.last_usage = provider.last_usage  # bound-method pass-through
    return wrapper
