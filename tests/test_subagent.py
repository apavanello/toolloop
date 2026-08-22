from __future__ import annotations

from conftest import FakeProvider
from toolloop import Agent, Status, subagent_tool

DELEGATE = (
    '{"type": "tool_call", "calls": [{"name": "delegate", "args": {"task": "explore everything"}}]}'
)
OUTER_FINAL = '{"type": "final_answer", "output": "outer done"}'
INNER_FINAL = '{"type": "final_answer", "output": "inner answer"}'


async def test_subagent_isolated_context():
    inner = FakeProvider([INNER_FINAL])
    outer = FakeProvider([DELEGATE, OUTER_FINAL])
    sub = subagent_tool(Agent(inner), name="delegate")
    result = await Agent(outer, tools=[sub]).run("go")
    assert result.status is Status.COMPLETED
    assert result.output == "outer done"
    # the sub-agent's final answer came back as the observation
    assert "inner answer" in outer.calls[1][-1].content
    # the inner conversation never saw the outer agent's tools
    assert "### delegate" not in inner.calls[0][0].content


async def test_subagent_reports_incomplete_status():
    from toolloop import RunResult

    class UnfinishedAgent:
        async def run(self, task: str, **kwargs) -> RunResult:
            return RunResult(Status.MAX_ITERATIONS, None, [])

    outer = FakeProvider([DELEGATE, OUTER_FINAL])
    sub = subagent_tool(UnfinishedAgent(), name="delegate")
    result = await Agent(outer, tools=[sub]).run("go")
    assert result.status is Status.COMPLETED
    assert "did not complete" in outer.calls[1][-1].content
