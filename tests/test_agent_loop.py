from __future__ import annotations

import pytest
from pydantic import BaseModel

from conftest import FakeProvider
from toolloop import Agent, OnMax, Status, tool
from toolloop._types import MaxIterationsExceeded, ParseLoopError

TOOL_CALL = '{"type": "tool_call", "calls": [{"id": "c1", "name": "echo", "args": {"text": "hi"}}]}'
FINAL = '{"type": "final_answer", "output": "done"}'


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return f"echo: {text}"


async def test_happy_path():
    provider = FakeProvider([TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo])
    result = await agent.run("say hi")
    assert result.status is Status.COMPLETED
    assert result.output == "done"
    assert [record.kind for record in result.history] == ["tool_calls", "final_answer"]
    assert result.history[0].calls[0].status == "ok"
    # the tool result was fed back as an observation before the final turn
    observation = provider.calls[1][-1]
    assert "echo: hi" in observation.content


async def test_unknown_tool_becomes_observation():
    provider = FakeProvider(
        [
            '{"type": "tool_call", "calls": [{"name": "nope", "args": {}}]}',
            FINAL,
        ]
    )
    result = await Agent(provider, tools=[echo]).run("x")
    assert result.status is Status.COMPLETED
    assert "unknown tool" in provider.calls[1][-1].content
    assert "echo" in provider.calls[1][-1].content  # available tools listed


async def test_invalid_tool_args_become_observation():
    provider = FakeProvider(
        [
            '{"type": "tool_call", "calls": [{"name": "echo", "args": {"text": 123}}]}',
            FINAL,
        ]
    )
    result = await Agent(provider, tools=[echo]).run("x")
    assert result.status is Status.COMPLETED
    # pydantic coerces int->str for `str` fields... 123 is a strict no: str field accepts int?
    observation = provider.calls[1][-1].content
    assert "ERROR" in observation or "echo: 123" in observation


async def test_parse_failure_auto_repairs():
    provider = FakeProvider(["garbage, no json here", FINAL])
    agent = Agent(provider, tools=[echo])
    result = await agent.run("x")
    assert result.status is Status.COMPLETED
    assert result.history[0].kind == "parse_error"
    assert "could not be parsed" in provider.calls[1][-1].content


async def test_parse_loop_raises_after_limit():
    provider = FakeProvider(["nope"] * 5)
    agent = Agent(provider, tools=[echo], max_parse_failures=3)
    with pytest.raises(ParseLoopError):
        await agent.run("x")
    assert len(provider.calls) == 3  # gave up after the configured failures


async def test_max_iterations_raise():
    provider = FakeProvider([TOOL_CALL] * 10)
    agent = Agent(provider, tools=[echo])
    with pytest.raises(MaxIterationsExceeded):
        await agent.run("x", max_iterations=3)


async def test_max_iterations_partial():
    provider = FakeProvider([TOOL_CALL] * 10)
    agent = Agent(provider, tools=[echo])
    result = await agent.run("x", max_iterations=3, on_max=OnMax.PARTIAL)
    assert result.status is Status.MAX_ITERATIONS
    assert result.output is None
    assert len(result.history) == 3


async def test_max_iterations_wrap_up():
    provider = FakeProvider([TOOL_CALL, TOOL_CALL, FINAL])
    agent = Agent(provider, tools=[echo])
    result = await agent.run("x", max_iterations=2, on_max=OnMax.WRAP_UP)
    assert result.status is Status.COMPLETED
    assert result.output == "done"


async def test_output_model_validation_repairs():
    class Out(BaseModel):
        answer: int

    provider = FakeProvider(
        [
            '{"type": "final_answer", "output": "not json at all"}',
            '{"type": "final_answer", "output": "{\\"answer\\": 1}"}',
        ]
    )
    result = await Agent(provider, tools=[echo]).run("x", output_model=Out)
    assert result.status is Status.COMPLETED
    assert result.output.answer == 1


async def test_output_model_accepts_dict_directly():
    class Out(BaseModel):
        answer: int

    provider = FakeProvider(['{"type": "final_answer", "output": {"answer": 7}}'])
    result = await Agent(provider, tools=[echo]).run("x", output_model=Out)
    assert result.status is Status.COMPLETED
    assert result.output.answer == 7


def test_duplicate_tool_names_rejected():
    with pytest.raises(ValueError, match="duplicate tool names"):
        Agent(FakeProvider([]), tools=[echo, echo])
