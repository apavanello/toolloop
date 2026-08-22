"""Example 01 — your first toolloop agent.

Runs fully offline: ``ScriptedProvider`` plays the LLM with pre-written
responses, so you can try it with zero setup:

    uv run python examples/01_first_agent.py

Every toolloop agent has three moving parts:

  1. PROVIDER — anything async that turns messages into text: your SDK, a
     plain HTTP call, a corporate proxy client, or a test double like the
     one below. This is the whole contract — no tool-use support needed.
  2. TOOLS — async functions decorated with ``@tool``. The name, description
     and argument schema come from the function itself (docstring + type
     hints), validated with pydantic.
  3. AGENT — owns the loop. It renders tool instructions into the system
     prompt, parses tool calls out of the model's plain-text response, runs
     the tools, feeds results back as "observations", and stops when the
     model answers with a ``final_answer`` envelope.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from toolloop import Agent, Message, tool


class ScriptedProvider:
    """Pre-written responses standing in for a real model."""

    def __init__(self, turns: list[str]):
        self.turns = list(turns)

    async def complete(self, messages: Sequence[Message]) -> str:
        print(f"[provider] {len(messages)} messages in -> scripted response")
        return self.turns.pop(0)


@tool
async def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


# What the (fake) model says on each turn. A real model produces this JSON
# envelope because the agent taught it the format in the system prompt.
SCRIPT = [
    '{"type": "tool_call", "calls": [{"id": "c1", "name": "add", "args": {"a": 2, "b": 3}}]}',
    '{"type": "final_answer", "output": "2 + 3 = 5"}',
]


async def main() -> None:
    agent = Agent(ScriptedProvider(SCRIPT), tools=[add])
    result = await agent.run("how much is 2 + 3?")

    print("status :", result.status)  # Status.COMPLETED
    print("output :", result.output)  # "2 + 3 = 5"
    print("history:")  # the full audit trail of the run
    for step in result.history:
        for call in step.calls:
            print(f"  step {step.step}: {call.name}{call.args} -> {call.status}: {call.result}")


if __name__ == "__main__":
    asyncio.run(main())
