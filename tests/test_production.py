from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from toolloop import Agent, AgentState, Status, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


# --- checkpoints ------------------------------------------------------------


async def test_checkpoint_path_written_at_run_end(tmp_path: Path):
    path = tmp_path / "session.json"
    provider = ScriptedProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    agent = Agent(provider, tools=[echo], checkpoint=str(path))
    await agent.run("x")

    state = AgentState.from_json(path.read_text())
    assert state.history[-1].kind == "final_answer"
    assert any("done" in m.content for m in state.messages)


async def test_periodic_checkpoints_respect_interval(tmp_path):
    saved: list[AgentState] = []

    async def sink(state: AgentState) -> None:
        saved.append(state)

    script = [tool_call("echo", call_id=f"c{i}", text=str(i)) for i in range(4)]
    script.append(final_answer("done"))
    provider = ScriptedProvider(script)
    agent = Agent(provider, tools=[echo], checkpoint=sink, checkpoint_every=2)
    await agent.run("x")

    # periodic (after steps 2 and 4) + forced final = 3 checkpoints
    assert len(saved) == 3
    assert [len(state.history) for state in saved] == [2, 4, 5]


async def test_checkpoint_failure_never_kills_the_run(tmp_path):
    def broken_sink(state: AgentState) -> None:
        raise RuntimeError("disk full")

    provider = ScriptedProvider([final_answer("done")])
    agent = Agent(provider, tools=[echo], checkpoint=broken_sink)
    result = await agent.run("x")
    assert result.status is Status.COMPLETED  # checkpoint error was swallowed


# --- usage ------------------------------------------------------------------


class UsageProvider(ScriptedProvider):
    """Reports per-call usage, like real SDKs do."""

    def last_usage(self):
        return {"prompt_tokens": 100, "completion_tokens": 40, "model": "demo"}


async def test_usage_summed_across_calls():
    provider = UsageProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    result = await Agent(provider, tools=[echo]).run("x")
    assert result.usage == {"prompt_tokens": 200, "completion_tokens": 80, "model": "demo"}


async def test_usage_none_when_provider_does_not_report():
    provider = ScriptedProvider([final_answer("done")])
    result = await Agent(provider, tools=[echo]).run("x")
    assert result.usage is None


# --- graceful cancellation --------------------------------------------------


@tool
async def slow_tool(seconds: float = 0.5) -> str:
    """Sleeps before answering."""
    await asyncio.sleep(seconds)
    return "finally done"


async def test_cancelled_run_preserves_conversation_for_resume():
    provider = ScriptedProvider([tool_call("slow_tool", call_id="c1", seconds=5)])
    agent = Agent(provider, tools=[slow_tool])

    task = asyncio.create_task(agent.run("x"))
    await asyncio.sleep(0.1)  # let it reach the tool
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # the conversation (input + tool call) survived the cancellation
    assert any("x" == m.content for m in agent.conversation)

    resumed = ScriptedProvider([final_answer("resumed")])
    agent2 = Agent.from_state(agent.to_state(), resumed, tools=[slow_tool])
    result = await agent2.run("and now?")
    assert result.output == "resumed"
    # the resumed provider saw the whole interrupted conversation
    contents = [m.content for m in resumed.calls[0]]
    assert "x" in contents and "and now?" == contents[-1]
