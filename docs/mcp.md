# MCP — Model Context Protocol

Expose any MCP server's tools to your agent — the whole MCP ecosystem for
free. Requires `pip install "toolloop[mcp]"`.

## Connecting

```python
from toolloop.mcp import McpServerConfig, mcp_tools

config = McpServerConfig(command="uvx", args=["mcp-server-fetch"])
# or streamable HTTP:
# config = McpServerConfig(url="https://example.com/mcp", headers={...})

async with mcp_tools(config) as tools:      # also accepts a list of configs
    agent = Agent(provider, tools=tools)    # tools are alive only inside the with
    await agent.run("fetch the toolloop README")
```

The context manager opens the transports (stdio subprocess or HTTP), performs
the MCP handshake, discovers the tools and yields `ToolDefinition`s. Sessions
close when the block exits — **run your agent inside the `async with`**.

## Multiple servers

```python
tools = []
async with mcp_tools([
    McpServerConfig(command="uvx", args=["mcp-server-fetch"]),
    McpServerConfig(url="https://example.com/mcp", prefix="corp_"),
]) as tools:
    ...
```

The optional `prefix` avoids name collisions across servers.

## Pass-through arguments

Arguments flow to the server **untouched**: the server's `inputSchema` is
rendered verbatim into the system prompt, and validation stays server-side
(per the MCP specification). Errors reported by the server (`isError`)
become repair observations for the model.

## Advanced: from an existing session

```python
from toolloop.mcp import mcp_tools_from_session

tools = await mcp_tools_from_session(session, dangerous=False, prefix="")
```

Use it when you manage the `ClientSession` yourself (or in tests).

!!! example
    A fully offline example — it spawns its own MCP server as a subprocess
    and connects through the real stdio transport — lives in
    [`examples/06_mcp_tools.py`](https://github.com/apavanello/toolloop/blob/main/examples/06_mcp_tools.py).
