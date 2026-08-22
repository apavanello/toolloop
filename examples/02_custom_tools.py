"""Example 02 — writing tools (and trusting the auto-repair loop).

Two things to internalize:

  * Invalid arguments and raised exceptions NEVER crash the loop. They become
    error observations, and the model fixes its own mistake on the next turn.
  * Returning a dict/list is serialized to JSON automatically; return a
    string when you want exact control over what the model sees.

Watch the scripted model call ``weather`` with ``days="three"`` (rejected by
pydantic), repair itself, then finish.

    uv run python examples/02_custom_tools.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from toolloop import Agent, Message, tool


class ScriptedProvider:
    def __init__(self, turns: list[str]):
        self.turns = list(turns)

    async def complete(self, messages: Sequence[Message]) -> str:
        return self.turns.pop(0)


@tool
async def weather(city: str, days: int = 1) -> dict:
    """Weather forecast for a city (pretend this hits a real API)."""
    forecast = ["sunny", "cloudy", "rainy"]
    return {"city": city, "days": days, "forecast": forecast[:days]}


@tool(dangerous=True)  # flagged: on_tool_call hooks can gate it (see example 03)
async def deploy(version: str) -> str:
    """Deploy a version to production."""
    return f"deployed {version}"


SCRIPT = [
    # wrong: days must be an int — pydantic rejects, model gets the error back
    '{"type": "tool_call", "calls": '
    '[{"id": "c1", "name": "weather", "args": {"city": "Lisbon", "days": "three"}}]}',
    # repaired on the next turn, no code involved
    '{"type": "tool_call", "calls": '
    '[{"id": "c2", "name": "weather", "args": {"city": "Lisbon", "days": 2}}]}',
    '{"type": "final_answer", "output": "Lisbon: sunny then cloudy"}',
]


async def main() -> None:
    agent = Agent(ScriptedProvider(SCRIPT), tools=[weather, deploy])
    result = await agent.run("weather in Lisbon for 2 days")

    print("output :", result.output)
    print("history:")
    for step in result.history:
        for call in step.calls:
            # the first call has status "error" — and that is fine
            print(f"  step {step.step}: {call.name} -> {call.status}: {call.result}")


if __name__ == "__main__":
    asyncio.run(main())
