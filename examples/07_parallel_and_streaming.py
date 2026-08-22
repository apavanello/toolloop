"""Example 07 — parallel tool calls and streaming.

Runs fully offline (scripted providers):

    uv run python examples/07_parallel_and_streaming.py

Part 1: the same three slow tools run sequentially (default) and in parallel
(``max_parallel_calls=3``) — watch the wall-clock difference.
Part 2: a provider that implements the optional ``stream()`` method, with an
``on_delta`` callback receiving tokens as they "arrive". The loop behaves
identically — streaming is UX only.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

from toolloop import Agent, tool
from toolloop.testing import ScriptedProvider, final_answer


@tool
async def fetch(url: str) -> str:
    """Fetch a URL (simulated latency)."""
    await asyncio.sleep(0.3)
    return f"200 OK from {url}"


def three_calls() -> str:
    entries = ",".join(
        f'{{"id": "c{i}", "name": "fetch", "args": {{"url": "https://x/{i}"}}}}' for i in range(3)
    )
    return f'{{"type": "tool_call", "calls": [{entries}]}}'


class StreamingScripted(ScriptedProvider):
    """Scripted provider that also implements the optional stream()."""

    async def stream(self, messages: Sequence):
        text = await self.complete(messages)  # consume the script as usual
        for start in range(0, len(text), 24):
            await asyncio.sleep(0.02)
            yield text[start : start + 24]


async def timed_run(label: str, **agent_kwargs) -> None:
    provider = ScriptedProvider([three_calls(), final_answer("fetched all three")])
    agent = Agent(provider, tools=[fetch], **agent_kwargs)
    started = time.perf_counter()
    result = await agent.run("fetch all three URLs")
    elapsed = time.perf_counter() - started
    print(f"{label:<28} {elapsed:.2f}s -> {result.output}")


async def main() -> None:
    print("--- Part 1: sequential (default) vs parallel ---")
    await timed_run("sequential (default)")
    await timed_run("max_parallel_calls=3", max_parallel_calls=3)
    # results are reassembled in call order either way; only the clock changes

    print("\n--- Part 2: streaming with on_delta ---")
    provider = StreamingScripted([three_calls(), final_answer("streamed and done")])
    agent = Agent(provider, tools=[fetch], on_delta=lambda delta: print(delta, end=""))
    result = await agent.run("fetch and stream")
    print(f"\nresult identical to non-streaming: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
