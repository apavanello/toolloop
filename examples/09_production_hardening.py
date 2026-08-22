"""Example 09 — production hardening.

Runs fully offline and fully SYNC — plain Python with no asyncio.run of our
own, demonstrating ``run_sync``:

    uv run python examples/09_production_hardening.py

Covers: dev logging, retries with backoff, provider timeout, rate limiting,
per-run usage and the sync facade.
"""

from __future__ import annotations

import asyncio
import time

from toolloop import Agent, rate_limited, run_sync, tool
from toolloop.devlog import dev_logger
from toolloop.testing import final_answer


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


class FlakyProvider:
    """A gateway that fails twice before recovering (blips happen)."""

    def __init__(self, payload: str, failures: int = 2):
        self.payload = payload
        self.failures = failures
        self.attempts = 0

    async def complete(self, messages):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("503 from the corporate gateway")
        return self.payload

    def last_usage(self):
        # real SDKs report this from the response object
        return {"prompt_tokens": 120, "completion_tokens": 30}


class HangingProvider:
    async def complete(self, messages):
        await asyncio.sleep(5)  # async sleep: the timeout CAN interrupt it
        return final_answer("too late")


class InstantProvider:
    async def complete(self, messages):
        return final_answer("ok")


async def three_spaced_calls(limited) -> None:
    await asyncio.gather(*(limited.complete([]) for _ in range(3)))


def main() -> None:
    dev_logger()  # one line: the agent narrates its run on stderr

    print("--- retries: transient failures recover transparently ---")
    flaky = FlakyProvider(final_answer("recovered"))
    result = run_sync(Agent(flaky, tools=[echo], max_retries=3, retry_backoff=0.05), "x")
    print(f"output after {flaky.attempts} attempts: {result.output}")
    print("usage summed by the run:", result.usage)

    print("\n--- provider timeout: fail fast instead of hanging ---")
    agent = Agent(HangingProvider(), tools=[echo], provider_timeout=0.3)
    started = time.perf_counter()
    try:
        run_sync(agent, "x")
    except TimeoutError:
        print(f"TimeoutError after {time.perf_counter() - started:.2f}s (not 5s)")

    print("\n--- rate limiting: shared wrapper = process-wide limit ---")
    limited = rate_limited(InstantProvider(), min_interval=0.15)
    started = time.perf_counter()
    asyncio.run(three_spaced_calls(limited))
    print(f"3 spaced calls took {time.perf_counter() - started:.2f}s (>= 0.30s)")


if __name__ == "__main__":
    main()
