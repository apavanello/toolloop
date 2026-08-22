"""Example 08 — session persistence and checkpoints.

Runs fully offline:

    uv run python examples/08_sessions_and_checkpoints.py

Part 1: snapshot a conversation (``to_state``/``to_json``), rebuild the agent
(``Agent.from_state``) and continue the SAME conversation — even "in another
process" (here, just a second agent with a second provider).
Part 2: incremental checkpoints — a callable (or a path) invoked every
``checkpoint_every`` steps and once at the end of the run. If the process
dies, you resume from the last checkpoint instead of losing the whole run.
"""

from __future__ import annotations

import asyncio

from toolloop import Agent, AgentState, Status, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


async def part1_resume() -> None:
    print("--- Part 1: save, serialize, resume ---")
    day_one = ScriptedProvider([final_answer("part-1: analysis done")])
    agent1 = Agent(day_one, tools=[echo])
    result1 = await agent1.run("analyze the logs")
    print("day one says:", result1.output)

    state = agent1.to_state()
    blob = state.to_json()  # persist this anywhere: file, DB, redis...
    print(f"serialized state: {len(blob)} chars, {len(state.messages)} messages")

    restored = AgentState.from_json(blob)
    day_two = ScriptedProvider([final_answer("part-2: report ready")])
    agent2 = Agent.from_state(restored, day_two, tools=[echo])
    result2 = await agent2.run("now write the report")

    # the second provider received the whole first-day conversation
    contents = [message.content for message in day_two.calls[0]]
    print("day two saw:", len(contents), "messages (incl. day one)")
    print("day two says:", result2.output)
    # audit history accumulates across the session
    print("session history:", [record.kind for record in result2.history])


async def part2_checkpoints() -> None:
    print("\n--- Part 2: incremental checkpoints ---")
    checkpoints: list[AgentState] = []

    async def save(state: AgentState) -> None:  # or: checkpoint="session.json"
        checkpoints.append(state)

    script = [tool_call("echo", call_id=f"c{i}", text=f"t{i}") for i in range(3)]
    provider = ScriptedProvider([*script, final_answer("done")])
    agent = Agent(provider, tools=[echo], checkpoint=save, checkpoint_every=1)
    result = await agent.run("step by step")

    assert result.status is Status.COMPLETED
    steps = [len(state.history) for state in checkpoints]
    print(f"checkpoints taken after steps: {steps}")
    # each checkpoint is a full resume point:
    print("latest checkpoint has", len(checkpoints[-1].messages), "messages")


async def main() -> None:
    await part1_resume()
    await part2_checkpoints()


if __name__ == "__main__":
    asyncio.run(main())
