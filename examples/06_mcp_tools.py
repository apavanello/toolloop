"""Example 06 — MCP servers as toolloop tools.

Runs fully offline: the example launches ITSELF as an MCP server subprocess
(the ``--serve`` branch below) and connects through the real stdio transport.
The child is told to serve via a CLI flag — argv is immune to the SDK's
minimal-default environment filtering, which strips custom env vars.

Requires the MCP extra: ``uv run --extra dev python examples/06_mcp_tools.py``
"""

from __future__ import annotations

import asyncio
import sys

from toolloop import Agent
from toolloop.mcp import McpServerConfig, mcp_tools
from toolloop.testing import ScriptedProvider, final_answer, tool_call

if "--serve" in sys.argv:  # we are the MCP server child process
    from fastmcp import FastMCP  # noqa: E402

    server = FastMCP("example-catalog")

    @server.tool
    def look_up(key: str) -> str:
        """Look up a key in the demo catalog."""
        catalog = {"pypi": "the Python package index", "mcp": "Model Context Protocol"}
        return catalog.get(key, "not found")

    server.run()
    sys.exit(0)


async def main() -> None:
    config = McpServerConfig(command=sys.executable, args=[__file__, "--serve"])

    async with mcp_tools(config) as tools:
        print("discovered from MCP:", [tool.name for tool in tools])

        provider = ScriptedProvider(
            [tool_call("look_up", call_id="c1", key="mcp"), final_answer("done")]
        )
        agent = Agent(provider, tools=tools)  # tools are alive only inside the with
        result = await agent.run("what is MCP?")

    print("output     :", result.output)
    print("observation:", result.history[0].calls[0].result)


if __name__ == "__main__":
    asyncio.run(main())
