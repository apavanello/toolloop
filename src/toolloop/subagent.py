"""Expose an Agent as a tool (isolated context, returns only the final answer)."""

from __future__ import annotations

from .agent import Agent, RunResult, Status
from .tools.definition import ToolDefinition, tool


def subagent_tool(
    agent: Agent, *, name: str = "subagent", description: str | None = None
) -> ToolDefinition:
    """Wrap ``agent`` as a tool.

    The sub-agent runs with its own isolated context: heavy exploration it
    performs never pollutes the caller's conversation — only its final answer
    comes back as the observation.
    """

    @tool(
        name=name,
        description=description
        or (
            "Delegate a self-contained task to a sub-agent with its own context "
            "window. Describe the task completely; returns the sub-agent's "
            "final answer."
        ),
    )
    async def _subagent(task: str) -> str:
        result: RunResult = await agent.run(task)
        if result.status is not Status.COMPLETED:
            return f"subagent did not complete (status={result.status.value})"
        return str(result.output)

    return _subagent
