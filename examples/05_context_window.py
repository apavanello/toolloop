"""Example 05 — keeping the context window in check.

``max_context_tokens`` enables two-stage context management:

  stage 1 — the OLDEST tool observations are truncated to a short preview;
  stage 2 — still over budget? the middle of the conversation is compacted
            by asking the provider itself for a summary. The system prompt
            and the most recent messages are always preserved.

Part 1 below drives a ``ContextManager`` directly on a hand-built
conversation (deterministic); Part 2 runs an Agent that logs its context
size at every step, so you can watch it being kept in check.

    uv run python examples/05_context_window.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from toolloop import Agent, ContextManager, Message, Role, tool
from toolloop.context import estimate_tokens


class ScriptedProvider:
    """Answers tool calls on demand; handles summarization requests, too."""

    def __init__(self):
        self.turns: list[str] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        if messages[0].content.startswith("Summarize"):
            return "(compact summary of the earlier exploration)"
        if len(self.turns) < 3:
            self.turns.append("used")
            return (
                '{"type": "tool_call", "calls": '
                '[{"id": "c1", "name": "verbose", "args": {"text": "go"}}]}'
            )
        return '{"type": "final_answer", "output": "done"}'


@tool
async def verbose(text: str) -> str:
    """A tool with heavy output (imagine a huge file read)."""
    return "x" * 600


def part1_context_manager() -> None:
    print("--- Part 1: ContextManager on a hand-built conversation ---")
    provider = ScriptedProvider()
    manager = ContextManager(provider, max_tokens=700)
    messages = [
        Message(Role.SYSTEM, "s" * 400),
        Message(Role.USER, "explore the codebase"),
    ]
    for index in range(4):
        messages.append(Message(Role.ASSISTANT, f"turn {index}"))
        messages.append(Message(Role.USER, "x" * 800, kind="observation"))

    print("before:", estimate_tokens(messages), "tokens,", len(messages), "messages")
    managed = asyncio.run(manager.manage(messages))
    print("after :", estimate_tokens(managed), "tokens,", len(managed), "messages")
    for message in managed:
        marker = " [truncated]" if "older observation truncated" in message.content else ""
        print(f"  {message.role.value:9} {len(message.content):5} chars{marker}")


async def part2_agent() -> None:
    print("\n--- Part 2: agent with max_context_tokens ---")

    async def log_size(ctx) -> None:
        chars = sum(len(m.content) for m in ctx.messages)
        print(f"  step {ctx.step}: {len(ctx.messages)} messages, {chars} chars total")

    agent = Agent(
        ScriptedProvider(),
        tools=[verbose],
        max_context_tokens=700,
        on_step=log_size,
    )
    result = await agent.run("explore until done")
    print("output:", result.output)


def part3_token_counter() -> None:
    print("\n--- Part 3: pluggable token counter ---")

    def exact_chars(messages):  # any policy you like — even tiktoken
        return sum(len(m.content) for m in messages)

    manager = ContextManager(
        ScriptedProvider(),
        max_tokens=1_000,
        token_counter=exact_chars,  # default heuristic is ~chars/4
    )
    messages = [Message(Role.SYSTEM, "s" * 400), Message(Role.USER, "x" * 500)]
    # 900 exact chars < 1000 budget -> untouched, even though the ~chars/4
    # heuristic would also pass; flip the numbers to see management kick in.
    managed = asyncio.run(manager.manage(messages))
    print("exact-char budget respected:", managed is messages)


def main() -> None:
    part1_context_manager()
    asyncio.run(part2_agent())
    part3_token_counter()


if __name__ == "__main__":
    main()
