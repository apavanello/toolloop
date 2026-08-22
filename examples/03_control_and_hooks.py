"""Example 03 — control modes and hooks.

Two control modes, set on the Agent (or overridden per run()):

  ControlMode.BYPASS  (default) — autonomous. Hooks may still veto or
    rewrite any call: returning ``None`` means "default-allow".
  ControlMode.APPROVE — default-deny. Every tool call must receive an
    explicit ``Decision.allow()`` from an ``on_tool_call`` hook — that is
    your human-in-the-loop hook point.

The same scenario runs twice below: a watchdog in BYPASS mode blocks the
dangerous tool, and a (fake) human approver in APPROVE mode denies the
dangerous call, rewrites one argument, and allows the rest. ``on_step`` and
``on_tool_result`` give you logging in both modes.

    uv run python examples/03_control_and_hooks.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from toolloop import Agent, ControlMode, Decision, Message, tool


class ScriptedProvider:
    def __init__(self, turns: list[str]):
        self.turns = list(turns)

    async def complete(self, messages: Sequence[Message]) -> str:
        return self.turns.pop(0)


@tool
async def read_config(key: str) -> str:
    """Read a configuration key."""
    return f"{key}=postgres://prod"


@tool(dangerous=True)
async def drop_database(confirm: bool) -> str:
    """Drop the production database (obviously dangerous)."""
    return "database dropped (yikes)"


# The model tries the dangerous call first, then reads config, then answers.
SCENARIO = [
    '{"type": "tool_call", "calls": '
    '[{"id": "c1", "name": "drop_database", "args": {"confirm": true}}]}',
    '{"type": "tool_call", "calls": '
    '[{"id": "c2", "name": "read_config", "args": {"key": "db_host"}}]}',
    '{"type": "final_answer", "output": "inspected the config safely"}',
]


async def log_steps(ctx) -> None:
    calls = ", ".join(f"{c.name}({c.status})" for c in ctx.calls) or "-"
    print(f"  [on_step] step {ctx.step} ({ctx.kind}): {calls}")


async def run_bypass() -> None:
    print("--- BYPASS: autonomous, watchdog may veto ---")

    async def watchdog(ctx) -> Decision | None:
        if ctx.dangerous:
            return Decision.deny("blocked by watchdog: dangerous tool")
        return None  # None in BYPASS = default-allow

    agent = Agent(
        ScriptedProvider(list(SCENARIO)),
        tools=[read_config, drop_database],
        on_tool_call=watchdog,
        on_step=log_steps,
    )
    result = await agent.run("inspect the database setup")
    print("  output:", result.output, "\n")


async def run_approve() -> None:
    print("--- APPROVE: default-deny, human-in-the-loop (simulated) ---")

    async def human(ctx) -> Decision:
        answer = "n" if ctx.dangerous else "y"  # stand-in for input()
        print(f"  [human] allow {ctx.name}{ctx.args}? {answer}")
        if answer == "n":
            return Decision.deny("human said no")
        if ctx.name == "read_config":
            # hooks can also rewrite the arguments before execution
            return Decision.allow(args={**ctx.args, "key": "db_host_rewritten"})
        return Decision.allow()

    agent = Agent(
        ScriptedProvider(list(SCENARIO)),
        tools=[read_config, drop_database],
        control=ControlMode.APPROVE,
        on_tool_call=human,
        on_step=log_steps,
    )
    result = await agent.run("inspect the database setup")
    print("  output:", result.output)


async def main() -> None:
    await run_bypass()
    await run_approve()


if __name__ == "__main__":
    asyncio.run(main())
