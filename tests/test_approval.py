from __future__ import annotations

from toolloop import Agent, ControlMode, Status, console_approver, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def safe_tool(value: int) -> int:
    """A safe tool."""
    return value


@tool(dangerous=True)
async def risky() -> str:
    """A dangerous tool."""
    return "ran"


async def test_safe_tools_allowed_without_asking():
    asked: list[str] = []

    def fake_prompt(question: str) -> str:
        asked.append(question)
        return "n"

    provider = ScriptedProvider([tool_call("safe_tool", value=1), final_answer("ok")])
    agent = Agent(
        provider,
        tools=[safe_tool, risky],
        control=ControlMode.APPROVE,
        on_tool_call=console_approver(prompt=fake_prompt),
    )
    result = await agent.run("x")
    assert result.history[0].calls[0].status == "ok"
    assert asked == []  # a human is never bothered with safe tools


async def test_dangerous_tool_denied_when_human_says_no():
    provider = ScriptedProvider([tool_call("risky"), final_answer("ok")])
    agent = Agent(
        provider,
        tools=[safe_tool, risky],
        control=ControlMode.APPROVE,
        on_tool_call=console_approver(prompt=lambda question: "n"),
    )
    result = await agent.run("x")
    assert result.history[0].calls[0].status == "denied"
    assert "DENIED" in provider.calls[1][-1].content


async def test_dangerous_tool_allowed_when_human_says_yes():
    provider = ScriptedProvider([tool_call("risky"), final_answer("ok")])
    agent = Agent(
        provider,
        tools=[safe_tool, risky],
        control=ControlMode.APPROVE,
        on_tool_call=console_approver(prompt=lambda question: "y"),
    )
    result = await agent.run("x")
    assert result.status is Status.COMPLETED
    assert result.history[0].calls[0].status == "ok"
    assert "ran" in provider.calls[1][-1].content
