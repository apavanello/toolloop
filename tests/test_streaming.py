from __future__ import annotations

from toolloop import Agent, Status, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


class StreamingScriptedProvider(ScriptedProvider):
    """Scripted provider that also implements the optional stream() method."""

    def __init__(self, responses, chunk_size: int = 12):
        super().__init__(responses)
        self.chunk_size = chunk_size
        self.stream_used = False

    async def stream(self, messages):
        self.stream_used = True
        text = await self.complete(messages)  # consume the script
        for start in range(0, len(text), self.chunk_size):
            yield text[start : start + self.chunk_size]


async def test_deltas_forwarded_and_loop_unchanged():
    provider = StreamingScriptedProvider(
        [tool_call("echo", call_id="c1", text="hi"), final_answer("done")]
    )
    deltas: list[str] = []

    async def on_delta(delta: str) -> None:
        deltas.append(delta)

    agent = Agent(provider, tools=[echo], on_delta=on_delta)
    result = await agent.run("x")

    assert result.status is Status.COMPLETED
    assert provider.stream_used
    assert len(deltas) > 2  # responses really arrived in chunks
    assert "".join(deltas) == tool_call("echo", call_id="c1", text="hi") + final_answer("done")
    # tool result flowed back exactly like in non-streaming mode
    assert "[c1] hi" in provider.calls[1][-1].content


async def test_provider_with_stream_but_no_on_delta_uses_complete():
    provider = StreamingScriptedProvider([final_answer("done")])
    agent = Agent(provider, tools=[echo])  # no on_delta configured
    result = await agent.run("x")
    assert result.output == "done"
    assert not provider.stream_used


async def test_sync_on_delta_callback_works():
    provider = StreamingScriptedProvider([final_answer("done")])
    deltas: list[str] = []
    agent = Agent(provider, tools=[echo], on_delta=deltas.append)
    await agent.run("x")
    assert "".join(deltas) == final_answer("done")
