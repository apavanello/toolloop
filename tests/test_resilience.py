from __future__ import annotations

import asyncio
import time

import pytest

from toolloop import Agent, Status, rate_limited, tool
from toolloop.testing import final_answer


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


class FlakyProvider:
    """Fails the first N calls, then succeeds."""

    def __init__(self, failures: int, payload: str):
        self.failures = failures
        self.payload = payload
        self.attempts = 0

    async def complete(self, messages):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("transient gateway error")
        return self.payload


async def test_retries_recover_from_transient_failures():
    provider = FlakyProvider(2, final_answer("recovered"))
    agent = Agent(provider, tools=[echo], max_retries=3, retry_backoff=0.01)
    result = await agent.run("x")
    assert result.status is Status.COMPLETED
    assert result.output == "recovered"
    assert provider.attempts == 3  # two failures + one success


async def test_retries_exhausted_raises_last_error():
    provider = FlakyProvider(10, final_answer("never"))
    agent = Agent(provider, tools=[echo], max_retries=2, retry_backoff=0.01)
    with pytest.raises(ConnectionError, match="transient gateway error"):
        await agent.run("x")
    assert provider.attempts == 3  # initial + 2 retries


async def test_no_retries_by_default():
    provider = FlakyProvider(1, final_answer("never"))
    agent = Agent(provider, tools=[echo])
    with pytest.raises(ConnectionError):
        await agent.run("x")
    assert provider.attempts == 1


class HangingProvider:
    async def complete(self, messages):
        await asyncio.sleep(30)
        return final_answer("late")


async def test_provider_timeout_fails_fast():
    agent = Agent(HangingProvider(), tools=[echo], provider_timeout=0.1)
    with pytest.raises(TimeoutError):
        await agent.run("x")


async def test_cancellation_is_never_retried():
    class CancelledOnce:
        def __init__(self):
            self.attempts = 0

        async def complete(self, messages):
            self.attempts += 1
            raise asyncio.CancelledError()

    provider = CancelledOnce()
    agent = Agent(provider, tools=[echo], max_retries=5, retry_backoff=0.01)
    with pytest.raises(asyncio.CancelledError):
        await agent.run("x")
    assert provider.attempts == 1  # propagated immediately


# --- rate_limited -----------------------------------------------------------


class SlowProvider:
    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.calls = 0

    async def complete(self, messages):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return final_answer("ok")

    def last_usage(self):
        return {"prompt_tokens": 10}


async def test_rate_limited_concurrency_cap():
    provider = SlowProvider()
    limited = rate_limited(provider, concurrency=1)
    # three concurrent completes through the same wrapper, one at a time
    started = time.perf_counter()
    await asyncio.gather(*(limited.complete([]) for _ in range(3)))
    elapsed = time.perf_counter() - started
    assert elapsed >= 0.6  # 3 x 0.2s serialized
    assert provider.calls == 3


async def test_rate_limited_allows_concurrency():
    provider = SlowProvider()
    limited = rate_limited(provider, concurrency=3)
    started = time.perf_counter()
    await asyncio.gather(*(limited.complete([]) for _ in range(3)))
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5  # ran concurrently (~0.2s)


async def test_rate_limited_min_interval():
    provider = SlowProvider(delay=0.0)
    limited = rate_limited(provider, min_interval=0.1)
    started = time.perf_counter()
    await asyncio.gather(*(limited.complete([]) for _ in range(3)))
    elapsed = time.perf_counter() - started
    assert elapsed >= 0.2  # spacing: at least 2 x interval between 3 calls


async def test_rate_limited_forwards_last_usage():
    limited = rate_limited(SlowProvider(delay=0.0), concurrency=2)
    assert callable(getattr(limited, "last_usage", None))
    await limited.complete([])
    assert limited.last_usage() == {"prompt_tokens": 10}


def test_rate_limited_passthrough_without_options():
    provider = SlowProvider()
    assert rate_limited(provider) is provider
