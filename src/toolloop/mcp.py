"""Bridge: expose MCP (Model Context Protocol) servers as toolloop tools.

Requires the MCP SDK: ``pip install "toolloop[mcp]"``. Tools are alive only
while the underlying MCP sessions are — run your agent *inside* the context::

    from toolloop.mcp import McpServerConfig, mcp_tools

    config = McpServerConfig(command="uvx", args=["mcp-server-fetch"])
    async with mcp_tools(config) as tools:
        agent = Agent(provider, tools=tools)
        await agent.run("fetch the toolloop README")

Arguments are passed through untouched (the MCP server validates them per its
own ``inputSchema``, which is rendered verbatim into the system prompt).
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic import ConfigDict, create_model

from .tools.definition import ToolDefinition

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError as exc:  # pragma: no cover - exercised only without the SDK
    raise ImportError('the MCP bridge requires the MCP SDK: pip install "toolloop[mcp]"') from exc

try:  # the helper was renamed between SDK 1.x and 2.0
    from mcp.client.streamable_http import streamable_http_client
except ImportError:  # pragma: no cover
    from mcp.client.streamable_http import streamablehttp_client as streamable_http_client


@dataclass
class McpServerConfig:
    """Connection to one MCP server: a stdio command OR an HTTP URL."""

    command: str | None = None  # stdio: executable to launch
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    url: str | None = None  # streamable HTTP endpoint
    headers: dict[str, str] | None = None
    prefix: str = ""  # optional tool-name prefix (avoids cross-server collisions)

    def __post_init__(self) -> None:
        if bool(self.command) == bool(self.url):
            raise ValueError("set exactly one of command= (stdio) or url= (HTTP)")


@asynccontextmanager
async def mcp_tools(configs: McpServerConfig | list[McpServerConfig], *, dangerous: bool = False):
    """Discover tools from one or more MCP servers.

    Yields a ``list[ToolDefinition]`` usable directly by ``Agent(tools=...)``.
    Sessions and transports close when the context exits.
    """
    config_list = [configs] if isinstance(configs, McpServerConfig) else list(configs)
    async with AsyncExitStack() as stack:
        tools: list[ToolDefinition] = []
        for config in config_list:
            session = await stack.enter_async_context(_open_session(config))
            tools.extend(
                await mcp_tools_from_session(session, dangerous=dangerous, prefix=config.prefix)
            )
        yield tools


@asynccontextmanager
async def _open_session(config: McpServerConfig):
    if config.url:
        async with streamable_http_client(config.url, headers=config.headers) as transport:
            read_stream, write_stream, *_ = transport
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
    else:
        parameters = StdioServerParameters(command=config.command, args=config.args, env=config.env)
        async with stdio_client(parameters) as transport:
            read_stream, write_stream = transport
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


async def mcp_tools_from_session(
    session, *, dangerous: bool = False, prefix: str = ""
) -> list[ToolDefinition]:
    """Wrap the tools of an already-initialized ``ClientSession``.

    Exposed for advanced use and tests; prefer :func:`mcp_tools`.
    """
    response = await session.list_tools()
    return [
        _wrap_tool(session, tool, dangerous=dangerous, prefix=prefix) for tool in response.tools
    ]


def _wrap_tool(session, tool, *, dangerous: bool, prefix: str) -> ToolDefinition:
    input_schema = dict(getattr(tool, "inputSchema", None) or {})
    args_model = create_model(
        f"{tool.name}__mcp_args",
        __config__=ConfigDict(extra="allow"),
    )

    async def _call(**kwargs: Any) -> str:
        result = await session.call_tool(tool.name, kwargs)
        text = "\n".join(
            block.text for block in (result.content or []) if getattr(block, "text", None)
        )
        if getattr(result, "isError", False):
            raise RuntimeError(text or "MCP tool error")
        return text or "(no content)"

    return ToolDefinition(
        name=f"{prefix}{tool.name}",
        description=getattr(tool, "description", None) or "",
        args_model=args_model,
        func=_call,
        dangerous=dangerous,
        schema=input_schema,
    )
