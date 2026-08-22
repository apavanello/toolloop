from __future__ import annotations

import json

import pytest

from toolloop import Agent, AgentState, Message, Role, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


async def test_state_round_trip_via_json():
    provider = ScriptedProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    agent = Agent(provider, tools=[echo])
    await agent.run("x")
    state = agent.to_state()

    restored = AgentState.from_json(state.to_json())
    assert [m.content for m in restored.messages] == [m.content for m in state.messages]
    assert [m.kind for m in restored.messages] == [m.kind for m in state.messages]
    assert [r.kind for r in restored.history] == ["tool_calls", "final_answer"]
    assert restored.history[0].calls[0].name == "echo"
    assert restored.history[0].calls[0].result == "hi"
    assert restored.history[0].calls[0].duration >= 0
    assert restored.version == 1
    assert restored.created_at


def test_state_rejects_unknown_version():
    raw = json.dumps({"version": 99, "messages": [], "history": []})
    with pytest.raises(ValueError, match="version"):
        AgentState.from_json(raw)


async def test_resume_continues_conversation():
    first = ScriptedProvider([final_answer("part-1")])
    agent1 = Agent(first, tools=[echo])
    await agent1.run("first task")

    second = ScriptedProvider([final_answer("part-2")])
    agent2 = Agent.from_state(agent1.to_state(), second, tools=[echo])
    result = await agent2.run("second task")

    assert result.output == "part-2"
    sent = second.calls[0]
    contents = [message.content for message in sent]
    assert sent[0].role is Role.SYSTEM
    assert contents[1] == "first task"
    assert contents[2] == final_answer("part-1")  # raw assistant envelope is stored
    assert contents[-1] == "second task"
    # audit history accumulates across the session
    assert [record.kind for record in result.history] == ["final_answer", "final_answer"]


async def test_resume_preserves_observation_kinds_for_truncation():
    messages = [Message(Role.SYSTEM, "s" * 400), Message(Role.USER, "task")]
    for _ in range(4):
        messages.append(Message(Role.ASSISTANT, "a" * 100))
        messages.append(Message(Role.USER, "x" * 1000, kind="observation"))
    state = AgentState(messages=messages)

    agent = Agent.from_state(state, ScriptedProvider([]), tools=[echo], max_context_tokens=1000)
    assert agent.context is not None
    managed = await agent.context.manage(list(agent.conversation))
    assert sum("older observation truncated" in m.content for m in managed) == 2
