from __future__ import annotations

from conftest import FakeProvider
from toolloop import Agent, Message, Role, Status, estimate_tokens, tool
from toolloop.context import ContextManager

TOOL_CALL = (
    '{"type": "tool_call", "calls": [{"id": "c1", "name": "verbose", "args": {"text": "hi"}}]}'
)
FINAL = '{"type": "final_answer", "output": "done"}'


@tool
async def verbose(text: str) -> str:
    """Echo with lots of padding."""
    return "x" * 1000


def test_estimate_tokens_grows_with_content():
    short = estimate_tokens([Message(Role.USER, "abcd")])
    long = estimate_tokens([Message(Role.USER, "a" * 4000)])
    assert 0 < short < long


async def test_manager_noop_under_budget():
    manager = ContextManager(FakeProvider([]), max_tokens=100_000)
    messages = [
        Message(Role.SYSTEM, "system"),
        Message(Role.USER, "hello", kind="observation"),
    ]
    assert await manager.manage(messages) is messages


async def test_truncation_of_old_observations():
    provider = FakeProvider([])  # must stay empty: truncation alone has to suffice
    manager = ContextManager(provider, max_tokens=1100)
    messages = [
        Message(Role.SYSTEM, "s" * 1000),
        Message(Role.USER, "task"),
    ]
    for _ in range(4):
        messages.append(Message(Role.ASSISTANT, "a" * 100))
        messages.append(Message(Role.USER, "x" * 1000, kind="observation"))

    result = await manager.manage(messages)

    truncated = [m for m in result if "older observation truncated" in m.content]
    assert len(truncated) == 2  # oldest two observations cut to a preview
    intact = [m for m in result if m.kind == "observation" and "x" * 1000 in m.content]
    assert len(intact) == 2  # the two most recent stay whole
    assert result[0].role is Role.SYSTEM and "s" * 1000 in result[0].content
    assert provider.calls == []  # no summarization call was needed


async def test_compaction_via_summarization():
    provider = FakeProvider([TOOL_CALL, "compressed: model looked at files", FINAL])
    agent = Agent(provider, tools=[verbose], max_context_tokens=300)
    result = await agent.run("original task")
    assert result.status is Status.COMPLETED
    # second provider call was the summarization request
    summary_request = provider.calls[1]
    assert "Summarize" in summary_request[0].content
    # the final call carries the summary marker, system prompt and recent tail
    final_messages = provider.calls[2]
    assert any("[conversation summary]" in m.content for m in final_messages)
    assert final_messages[0].role is Role.SYSTEM
