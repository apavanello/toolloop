from __future__ import annotations

import pytest

from toolloop import Agent, Status, run_sync, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


def test_run_sync_happy_path():
    provider = ScriptedProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    agent = Agent(provider, tools=[echo])
    result = run_sync(agent, "x")
    assert result.status is Status.COMPLETED
    assert result.output == "done"


async def test_run_sync_refuses_running_loop():
    provider = ScriptedProvider([final_answer("done")])
    agent = Agent(provider, tools=[echo])
    with pytest.raises(RuntimeError, match="await agent.run"):
        run_sync(agent, "x")
