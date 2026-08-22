from __future__ import annotations

import asyncio
import time

import pytest

from toolloop import Agent, Decision, Status, tool
from toolloop.testing import ScriptedProvider, final_answer

executions: list[str] = []


@tool
async def slow(tag: str) -> str:
    """A tool that takes a while."""
    executions.append(tag)
    await asyncio.sleep(0.2)
    return f"done:{tag}"


CALLS = (
    '{"type": "tool_call", "calls": ['
    '{"id": "a", "name": "slow", "args": {"tag": "a"}}, '
    '{"id": "b", "name": "slow", "args": {"tag": "b"}}, '
    '{"id": "c", "name": "slow", "args": {"tag": "c"}}]}'
)


async def test_sequential_by_default():
    provider = ScriptedProvider([CALLS, final_answer("ok")])
    agent = Agent(provider, tools=[slow])
    started = time.perf_counter()
    result = await agent.run("x")
    elapsed = time.perf_counter() - started
    assert result.status is Status.COMPLETED
    assert elapsed >= 0.6  # three 0.2s sleeps, one after another


async def test_parallel_execution_preserves_order():
    provider = ScriptedProvider([CALLS, final_answer("ok")])
    agent = Agent(provider, tools=[slow], max_parallel_calls=3)
    started = time.perf_counter()
    result = await agent.run("x")
    elapsed = time.perf_counter() - started
    assert result.status is Status.COMPLETED
    assert elapsed < 0.5  # concurrent (~0.2s); sequential would be 0.6s+

    records = result.history[0].calls
    assert [record.call_id for record in records] == ["a", "b", "c"]
    assert [record.result for record in records] == ["done:a", "done:b", "done:c"]
    observation = provider.calls[1][-1].content
    assert observation.index("done:a") < observation.index("done:b")
    assert observation.index("done:b") < observation.index("done:c")


async def test_semaphore_caps_concurrency():
    provider = ScriptedProvider([CALLS, final_answer("ok")])
    agent = Agent(provider, tools=[slow], max_parallel_calls=2)
    started = time.perf_counter()
    await agent.run("x")
    elapsed = time.perf_counter() - started
    assert 0.4 <= elapsed < 0.6  # two waves: (a,b) then (c)


async def test_gating_is_sequential_and_denied_calls_never_run():
    executions.clear()
    gate_order: list[str] = []

    async def gate(ctx) -> Decision:
        gate_order.append(ctx.call_id)
        if ctx.call_id == "b":
            return Decision.deny("not this one")
        return Decision.allow()

    provider = ScriptedProvider([CALLS, final_answer("ok")])
    agent = Agent(provider, tools=[slow], on_tool_call=gate, max_parallel_calls=3)
    result = await agent.run("x")

    assert gate_order == ["a", "b", "c"]  # approvals asked one by one
    assert executions == ["a", "c"]  # denied call never executed
    statuses = {record.call_id: record.status for record in result.history[0].calls}
    assert statuses == {"a": "ok", "b": "denied", "c": "ok"}


def test_invalid_max_parallel_calls_rejected():
    with pytest.raises(ValueError, match="max_parallel_calls"):
        Agent(ScriptedProvider([]), tools=[slow], max_parallel_calls=0)
