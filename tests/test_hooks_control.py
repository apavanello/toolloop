from __future__ import annotations

import pytest

from conftest import FakeProvider
from toolloop import Agent, ControlError, ControlMode, Decision, Status, tool

TOOL_CALL = '{"type": "tool_call", "calls": [{"id": "c1", "name": "echo", "args": {"text": "hi"}}]}'
FINAL = '{"type": "final_answer", "output": "done"}'


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return f"echo: {text}"


async def test_approve_mode_requires_hook():
    agent = Agent(FakeProvider([FINAL]), tools=[echo], control=ControlMode.APPROVE)
    with pytest.raises(ControlError):
        await agent.run("x")


async def test_approve_denies_when_hook_abstains():
    seen = []

    async def approver(ctx):
        seen.append(ctx)
        return None  # no verdict -> denied under APPROVE

    provider = FakeProvider([TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo], control=ControlMode.APPROVE, on_tool_call=approver)
    result = await agent.run("x")
    assert result.status is Status.COMPLETED
    assert result.history[0].calls[0].status == "denied"
    assert "DENIED" in provider.calls[1][-1].content
    assert seen[0].name == "echo"
    assert seen[0].dangerous is False


async def test_approve_allows_when_hook_allows():
    async def approver(ctx):
        return Decision.allow()

    provider = FakeProvider([TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo], control=ControlMode.APPROVE, on_tool_call=approver)
    result = await agent.run("x")
    assert result.history[0].calls[0].status == "ok"


async def test_bypass_respects_explicit_deny():
    async def veto(ctx):
        return Decision.deny("not allowed")

    provider = FakeProvider([TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo], on_tool_call=veto)
    result = await agent.run("x")
    assert result.history[0].calls[0].status == "denied"
    assert "not allowed" in provider.calls[1][-1].content


async def test_hook_can_modify_args():
    async def approver(ctx):
        return Decision.allow(args={"text": "modified"})

    provider = FakeProvider([TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo], on_tool_call=approver)
    result = await agent.run("x")
    assert result.history[0].calls[0].args == {"text": "modified"}
    assert "echo: modified" in provider.calls[1][-1].content


async def test_on_step_and_on_tool_result_fire():
    steps = []
    results = []

    async def on_step(ctx):
        steps.append((ctx.step, ctx.kind))

    async def on_tool_result(ctx):
        results.append(ctx.status)

    provider = FakeProvider([TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo], on_step=on_step, on_tool_result=on_tool_result)
    await agent.run("x")
    assert steps == [(1, "tool_calls"), (2, "final_answer")]
    assert results == ["ok"]


async def test_control_mode_overridable_per_run():
    agent = Agent(FakeProvider([FINAL]), tools=[echo])  # BYPASS by default
    with pytest.raises(ControlError):
        await agent.run("x", control=ControlMode.APPROVE)


async def test_dangerous_flag_reaches_hook():
    from toolloop.tools import bash

    seen = []

    async def approver(ctx):
        seen.append(ctx.dangerous)
        return Decision.allow()

    provider = FakeProvider(
        [
            '{"type": "tool_call", "calls": [{"name": "bash", "args": {"command": "true"}}]}',
            FINAL,
        ]
    )
    agent = Agent(provider, tools=[bash], on_tool_call=approver)
    await agent.run("x")
    assert seen == [True]
