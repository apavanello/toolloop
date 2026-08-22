# Tools

Tools are async functions. The `@tool` decorator derives everything from the
function itself: name, description and argument schema.

## Defining a tool

```python
from toolloop import tool


@tool
async def search_docs(query: str, limit: int = 5) -> str:
    """Search the internal documentation."""
    ...  # return a str, or anything JSON-serializable
```

- **Name** — the function name (override with `@tool(name="...")`)
- **Description** — the docstring (what the model reads to decide when to use it)
- **Schema** — type hints, validated with pydantic; defaults become optional
- **Return** — strings pass through verbatim; dicts/lists are serialized to JSON

## Errors never crash the loop

Invalid arguments (rejected by pydantic) and raised exceptions become error
observations the model can repair from:

```python
@tool
async def only_int(n: int) -> int:
    """Return n."""
    return n
```

A call with `{"n": "three"}` produces an observation like
`ERROR: invalid arguments (n: Input should be a valid integer)` — the model
corrects itself next turn.

## Dangerous tools

Flag tools that deserve a human gate:

```python
@tool(dangerous=True)
async def deploy(version: str) -> str:
    """Deploy a version to production."""
    ...
```

`dangerous` flows into the `on_tool_call` hook context — see
[Control & hooks](control.md) for how `console_approver` uses it.

## The standard toolset (optional)

```python
from toolloop import STD_TOOLS
# bash, read_file, write_file, edit_file, list_files, grep
```

A pure-Python coding-agent toolset. Results are **compact by design** (a write
tool confirms the size it wrote, it does not echo the content) — the
"trust the sub-execution" philosophy that keeps context small. Import it or
ignore it; the core knows nothing about it.

## MCP tools

Any Model Context Protocol server can contribute tools — see
[MCP](../mcp.md).

## Custom schemas (bridge authors)

`ToolDefinition` accepts a `schema=` override for tools that bring their own
JSON schema (the MCP bridge uses this to render the server's `inputSchema`
verbatim into the prompt).
