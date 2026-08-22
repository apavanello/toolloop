from __future__ import annotations

import types

import pytest

from toolloop.mcp import McpServerConfig, mcp_tools_from_session
from toolloop.protocol import JsonToolProtocol


class FakeSession:
    """Stands in for an initialized mcp.ClientSession."""

    def __init__(self, tools, results):
        self.tools = tools
        self.results = list(results)
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        return types.SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return self.results.pop(0)


def _fake_tool(name="look_up", description="Look a key up.", schema=None):
    return types.SimpleNamespace(
        name=name,
        description=description,
        inputSchema=schema or {"type": "object", "properties": {"key": {"type": "string"}}},
    )


def _fake_result(text, is_error=False):
    block = types.SimpleNamespace(type="text", text=text)
    return types.SimpleNamespace(content=[block], isError=is_error)


async def test_from_session_wraps_name_description_schema():
    session = FakeSession([_fake_tool()], [])
    tools = await mcp_tools_from_session(session, prefix="cat_")

    assert len(tools) == 1
    assert tools[0].name == "cat_look_up"
    assert tools[0].description == "Look a key up."
    assert tools[0].json_schema()["properties"]["key"]["type"] == "string"


async def test_arguments_pass_through_untouched():
    session = FakeSession([_fake_tool()], [_fake_result("found it")])
    tools = await mcp_tools_from_session(session)

    ok, observation = await tools[0].execute({"key": "pypi", "nested": {"deep": [1, 2]}})
    assert ok
    assert observation == "found it"
    # the server received the args exactly as the model produced them
    assert session.calls == [("look_up", {"key": "pypi", "nested": {"deep": [1, 2]}})]


async def test_isError_becomes_error_observation():
    session = FakeSession([_fake_tool()], [_fake_result("boom", is_error=True)])
    tools = await mcp_tools_from_session(session)

    ok, observation = await tools[0].execute({"key": "x"})
    assert not ok
    assert "RuntimeError" in observation and "boom" in observation


async def test_verbatim_schema_reaches_the_system_prompt():
    session = FakeSession([_fake_tool()], [])
    tools = await mcp_tools_from_session(session)
    rendered = JsonToolProtocol().render_instructions(tools)
    assert '"key"' in rendered and '"string"' in rendered


async def test_dangerous_flag_propagates():
    session = FakeSession([_fake_tool()], [])
    tools = await mcp_tools_from_session(session, dangerous=True)
    assert tools[0].dangerous is True


def test_server_config_requires_exactly_one_transport():
    with pytest.raises(ValueError, match="exactly one"):
        McpServerConfig()
    with pytest.raises(ValueError, match="exactly one"):
        McpServerConfig(command="uvx", url="https://example.com/mcp")


async def test_integration_real_fastmcp_over_stdio(tmp_path):
    """Full stack: FastMCP subprocess -> stdio transport -> bridge -> agent loop."""
    pytest.importorskip("fastmcp")
    import sys

    from toolloop import Agent
    from toolloop.mcp import mcp_tools
    from toolloop.testing import ScriptedProvider, final_answer, tool_call

    server_script = tmp_path / "server.py"
    server_script.write_text(
        "from fastmcp import FastMCP\n"
        "\n"
        "server = FastMCP('catalog')\n"
        "\n"
        "\n"
        "@server.tool\n"
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b\n"
        "\n"
        "server.run()\n"
    )
    config = McpServerConfig(command=sys.executable, args=[str(server_script)])
    async with mcp_tools(config) as tools:
        assert [tool.name for tool in tools] == ["add"]
        provider = ScriptedProvider(
            [tool_call("add", call_id="c1", a=2, b=3), final_answer("sum is 5")]
        )
        result = await Agent(provider, tools=tools).run("sum 2 and 3")

    assert result.output == "sum is 5"
    assert result.history[0].calls[0].status == "ok"
    assert result.history[0].calls[0].result == "5"
