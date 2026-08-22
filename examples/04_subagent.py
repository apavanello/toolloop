"""Example 04 — subagents: delegate with an isolated context.

``subagent_tool`` wraps an Agent as a tool. The sub-agent explores with its
OWN conversation window; only its ``final_answer`` flows back to the caller
as the observation. Use it for greedy exploration (read many files, grep
everywhere) without polluting the main context — the a2a-style "trust the
sub-execution" pattern.

    uv run python examples/04_subagent.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from toolloop import Agent, Message, subagent_tool, tool


class ScriptedProvider:
    def __init__(self, turns: list[str]):
        self.turns = list(turns)

    async def complete(self, messages: Sequence[Message]) -> str:
        self.last_messages = list(messages)
        return self.turns.pop(0)


@tool
async def write_report(content: str) -> str:
    """Persist the final report."""
    return f"saved {len(content)} chars"


# The explorer: in real life it would read_file/grep through a big repo,
# stuffing ITS context — never the caller's.
explorer = Agent(
    ScriptedProvider(
        [
            '{"type": "final_answer", "output": '
            '"3 pending TODOs in 2 files; tests are the bottleneck"}',
        ]
    ),
    tools=[],  # a sub-agent can itself have tools, sub-agents, hooks...
)

# The orchestrator: delegates the exploration, then writes a report.
orchestrator = Agent(
    ScriptedProvider(
        [
            '{"type": "tool_call", "calls": '
            '[{"id": "c1", "name": "explore", "args": {"task": "find pending TODOs"}}]}',
            '{"type": "tool_call", "calls": '
            '[{"id": "c2", "name": "write_report", '
            '"args": {"content": "TODO audit: 3 items in 2 files"}}]}',
            '{"type": "final_answer", "output": "report ready"}',
        ]
    ),
    tools=[subagent_tool(explorer, name="explore"), write_report],
)


async def main() -> None:
    result = await orchestrator.run("audit the TODOs and write a report")

    print("output :", result.output)
    for step in result.history:
        for call in step.calls:
            preview = call.result[:60].replace("\n", " ")
            print(f"  step {step.step}: {call.name} -> {call.status}: {preview}...")

    # The caller's context only ever saw the explorer's final answer —
    # whatever the explorer read internally stayed in its own window.


if __name__ == "__main__":
    asyncio.run(main())
