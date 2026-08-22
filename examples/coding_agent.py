"""A minimal coding-agent harness built with toolloop.

Usage:
    OPENAI_API_KEY=... uv run --extra openai python examples/coding_agent.py "task here"

Batteries shown: console approver (human gates dangerous tools only), dev
logging, retries/timeout, and an incremental checkpoint to resume after a
crash. Ready-made providers live in ``toolloop.providers``.
"""

from __future__ import annotations

import asyncio
import os
import sys

from toolloop import STD_TOOLS, Agent, ControlMode, OnMax, Status, console_approver
from toolloop.devlog import dev_logger
from toolloop.providers import OpenAICompatProvider


async def main() -> None:
    task = " ".join(sys.argv[1:]) or "List the Python files in this repo and count total lines."
    dev_logger()  # live narration of every step on stderr
    provider = OpenAICompatProvider(
        model=os.environ.get("TOOLLOOP_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("OPENAI_BASE_URL"),  # point at your corporate proxy
        api_key=os.environ.get("OPENAI_API_KEY"),
    )
    agent = Agent(
        provider,
        tools=STD_TOOLS,
        control=ControlMode.APPROVE,  # default-deny: hooks decide
        on_tool_call=console_approver(),  # safe tools pass, dangerous ask
        system_prompt="You are a careful coding agent working in the current directory.",
        max_context_tokens=16_000,
        max_retries=2,  # transient gateway blips
        provider_timeout=120,
        checkpoint=".toolloop-session.json",  # crash-resume with Agent.from_state
    )
    result = await agent.run(task, max_iterations=30, on_max=OnMax.WRAP_UP)

    print("status:", result.status.value)
    print("output:", result.output)
    for step in result.history:
        for call in step.calls:
            print(f"  step {step.step}: {call.name} -> {call.status}")
    sys.exit(0 if result.status is Status.COMPLETED else 1)


if __name__ == "__main__":
    asyncio.run(main())
