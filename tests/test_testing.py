from __future__ import annotations

import pytest

from toolloop.protocol import FinalAnswer, JsonToolProtocol, ToolCalls
from toolloop.testing import ScriptedProvider, final_answer, tool_call

protocol = JsonToolProtocol()


def test_tool_call_builder_parses():
    parsed = protocol.parse(tool_call("echo", call_id="c1", text="hi"))
    assert isinstance(parsed, ToolCalls)
    assert parsed.calls[0].id == "c1"
    assert parsed.calls[0].name == "echo"
    assert parsed.calls[0].args == {"text": "hi"}


def test_tool_call_builder_generates_id_when_absent():
    parsed = protocol.parse(tool_call("echo"))
    assert isinstance(parsed, ToolCalls)
    assert parsed.calls[0].id  # framework fills one in


def test_final_answer_builder_parses_any_output():
    parsed = protocol.parse(final_answer({"answer": 1}))
    assert isinstance(parsed, FinalAnswer)
    assert parsed.output == {"answer": 1}


async def test_scripted_provider_records_and_exhausts():
    provider = ScriptedProvider([final_answer("done"), final_answer("more")])
    assert await provider.complete([]) == final_answer("done")
    assert len(provider.calls) == 1
    assert await provider.complete([]) == final_answer("more")
    with pytest.raises(AssertionError, match="ran out of scripted responses"):
        await provider.complete([])
