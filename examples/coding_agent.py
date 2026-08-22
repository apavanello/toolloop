"""A minimal coding-agent harness built with toolloop.

Usage:
    OPENAI_API_KEY=... uv run python examples/coding_agent.py "task here"

Every tool call goes through the approval hook: safe tools run free, the
dangerous one (bash) asks a human first. Point it at any provider you like —
see openai_compat_provider.py and anthropic_provider.py.
"""

from __future__ import annotations

import asyncio
import os
import sys

from openai_compat_provider import OpenAICompatProvider

from toolloop import STD_TOOLS, Agent, ControlMode, Decision, OnMax, Status


async def approve(ctx) -> Decision:
    """Human-in-the-loop: only gate the tools marked as dangerous."""
    if not ctx.dangerous:
        return Decision.allow()
    answer = input(f"allow {ctx.name}({ctx.args})? [y/N] ")
    return Decision.allow() if answer.strip().lower() == "y" else Decision.deny("user said no")


async def main() -> None:
    task = " ".join(sys.argv[1:]) or "List the Python files in this repo and count total lines."
    provider = OpenAICompatProvider(
        model=os.environ.get("TOOLLOOP_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("OPENAI_BASE_URL"),  # point at your corporate proxy
        api_key=os.environ.get("OPENAI_API_KEY"),
    )
    agent = Agent(
        provider,
        tools=STD_TOOLS,
        control=ControlMode.APPROVE,
        on_tool_call=approve,
        system_prompt="You are a careful coding agent working in the current directory.",
        max_context_tokens=16_000,
    )
    result = await agent.run(task, max_iterations=30, on_max=OnMax.WRAP_UP)

    print("status:", result.status.value)
    print("output:", result.output)
    for step in result.history:
        for call in step.calls:
            print(f"  step {step.step}: {call.name} -> {call.status}")
    sys.exit(0 if result.status is Status.COMPLETED else 1)


asyncio.run(main())
