from __future__ import annotations

import pytest

from toolloop import ParseError, tool
from toolloop.protocol import FinalAnswer, JsonToolProtocol, ToolCalls


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


protocol = JsonToolProtocol()


def test_render_instructions_contains_schemas():
    rendered = protocol.render_instructions([echo])
    assert "### echo" in rendered
    assert "Echo the text." in rendered
    assert "tool_call" in rendered
    assert "final_answer" in rendered
    assert "properties" in rendered  # embedded JSON schema


def test_parse_fenced_tool_call_with_prose():
    text = (
        "Sure, let me call the tool.\n"
        '```json\n{"type": "tool_call", "calls": '
        '[{"name": "echo", "args": {"text": "hi"}}]}\n```\n'
        "That is my call."
    )
    parsed = protocol.parse(text)
    assert isinstance(parsed, ToolCalls)
    assert parsed.calls[0].name == "echo"
    assert parsed.calls[0].args == {"text": "hi"}
    assert parsed.calls[0].id  # generated when the model omits it


def test_parse_last_fenced_block_wins():
    text = (
        '```json\n{"type": "final_answer", "output": "draft"}\n```\n'
        '```json\n{"type": "final_answer", "output": "final"}\n```'
    )
    parsed = protocol.parse(text)
    assert isinstance(parsed, FinalAnswer)
    assert parsed.output == "final"


def test_parse_bare_json_without_fence():
    parsed = protocol.parse('{"type": "final_answer", "output": 42}')
    assert isinstance(parsed, FinalAnswer)
    assert parsed.output == 42


def test_parse_multiple_calls():
    text = (
        '{"type": "tool_call", "calls": ['
        '{"id": "a", "name": "echo", "args": {"text": "1"}}, '
        '{"id": "b", "name": "echo", "args": {"text": "2"}}]}'
    )
    parsed = protocol.parse(text)
    assert isinstance(parsed, ToolCalls)
    assert [call.id for call in parsed.calls] == ["a", "b"]


def test_parse_error_on_plain_prose():
    with pytest.raises(ParseError) as excinfo:
        protocol.parse("I will not use tools, sorry!")
    assert "final_answer" in excinfo.value.reason


def test_parse_error_on_bad_envelope_type():
    with pytest.raises(ParseError):
        protocol.parse('```json\n{"type": "banana"}\n```')


def test_parse_error_on_empty_calls():
    with pytest.raises(ParseError):
        protocol.parse('{"type": "tool_call", "calls": []}')
