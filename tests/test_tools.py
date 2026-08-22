from __future__ import annotations

import pytest

from toolloop import tool
from toolloop.tools.definition import ToolDefinition


def test_tool_decorator_bare():
    @tool
    async def echo(text: str) -> str:
        """Echo the text."""
        return text

    assert isinstance(echo, ToolDefinition)
    assert echo.name == "echo"
    assert echo.description == "Echo the text."
    assert echo.json_schema()["properties"]["text"]["type"] == "string"
    assert echo.json_schema()["required"] == ["text"]


def test_tool_decorator_configured():
    @tool(name="runner", dangerous=True)
    async def run() -> str:
        """Run something."""
        return "ok"

    assert run.name == "runner"
    assert run.dangerous is True
    assert run.description == "Run something."


async def test_execute_ok_with_defaults():
    @tool
    async def add(a: int, b: int = 10) -> int:
        """Add numbers."""
        return a + b

    ok, result = await add.execute({"a": 1, "b": 2})
    assert ok and result == "3"

    ok, result = await add.execute({"a": 1})
    assert ok and result == "11"


async def test_execute_invalid_args_become_observation():
    @tool
    async def only_int(n: int) -> int:
        """Return n."""
        return n

    ok, result = await only_int.execute({"n": "not-an-int"})
    assert not ok and "invalid arguments" in result

    ok, result = await only_int.execute({"n": 1, "sneaky": True})
    assert not ok and "invalid arguments" in result


async def test_execute_exception_becomes_observation():
    @tool
    async def boom() -> str:
        """Explode."""
        raise ValueError("kaboom")

    ok, result = await boom.execute({})
    assert not ok and "ValueError: kaboom" in result


def test_tool_rejects_sync_function():
    with pytest.raises(TypeError):

        @tool
        def sync_tool(x: int) -> int:
            """Not async."""
            return x
