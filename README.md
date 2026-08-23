[English](https://github.com/apavanello/toolloop/blob/main/README.md) | [Português (BR)](https://github.com/apavanello/toolloop/blob/main/README.pt-br.md)

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%"
       alt="toolloop — agent loops for LLM providers without native tool use. Terminal panel showing a real agent run: tool_call envelope, tools executing, observation, final_answer.">
</p>

[![CI](https://github.com/apavanello/toolloop/actions/workflows/ci.yml/badge.svg)](https://github.com/apavanello/toolloop/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/toolloop?color=3FB950&label=PyPI)](https://pypi.org/project/toolloop/)
[![Python](https://img.shields.io/pypi/pyversions/toolloop?color=3FB950)](https://pypi.org/project/toolloop/)
[![License: MIT](https://img.shields.io/pypi/l/toolloop?color=3FB950)](LICENSE)

`toolloop` is a Python framework for building autonomous agents — tool use,
exploration, coding — on top of any LLM endpoint, even (especially) the ones
whose SDKs never exposed a `tools` parameter. If you can send messages and get
text back, you can run an agent on it.

> GitHub: <https://github.com/apavanello/toolloop> ·
> PyPI: <https://pypi.org/project/toolloop/> ·
> Docs: <https://apavanello.github.io/toolloop>

## Why

Plenty of real-world LLM access goes through proprietary corporate SDKs that
proxy the big providers (Anthropic, OpenAI, Kimi, DeepSeek, ...) but strip or
never implemented the tool-use layer. The models behind them are perfectly
capable of agentic work — the SDK just won't carry function calls.

`toolloop` solves this at the application layer:

- **Bring your own provider.** The framework never manages providers. The
  whole contract is one async method: `complete(messages) -> str`.
- **Tools over plain text.** Tool schemas are rendered into the system prompt;
  tool calls are parsed out of the model's text responses. Parse errors are
  fed back to the model (auto-repair) until it gets the envelope right.
- **Loop until satisfied.** Given an input, the agent calls tools, receives
  observations, and iterates until it emits a `final_answer`.

## Install

Requires Python 3.11+.

```bash
pip install toolloop                    # core (pydantic-only)
pip install "toolloop[all]"             # everything below in one go
pip install "toolloop[openai]"          # + OpenAICompat/OpenRouter adapters
pip install "toolloop[anthropic]"       # + Anthropic adapter
pip install "toolloop[otel]"            # + OpenTelemetry auto-instrumentation
pip install "toolloop[mcp]"             # + MCP (Model Context Protocol) bridge
```

From source: `uv sync --extra dev`.

## Quickstart (no LLM needed)

```python
import asyncio

from toolloop import Agent, tool


@tool
async def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class DemoProvider:
    """A scripted provider standing in for your real one."""

    def __init__(self):
        self.turns = [
            '{"type": "tool_call", "calls": [{"id": "c1", "name": "add", "args": {"a": 2, "b": 3}}]}',
            '{"type": "final_answer", "output": "2 + 3 = 5"}',
        ]

    async def complete(self, messages):
        return self.turns.pop(0)


agent = Agent(DemoProvider(), tools=[add])
result = asyncio.run(agent.run("how much is 2 + 3?"))
print(result.output)  # 2 + 3 = 5
print(result.status)  # Status.COMPLETED
print(result.history[0].calls[0].result)  # 5
```

## Bring your own provider

Implement one async method and you are done — SDK, plain HTTP, whatever:

```python
class MyCorporateProxyProvider:
    async def complete(self, messages):
        response = await my_corporate_sdk.chat(
            [{"role": m.role.value, "content": m.content} for m in messages]
        )
        return response.text
```

Or use a ready-made adapter from `toolloop.providers` (tested, with the
provider-specific quirks handled — e.g. OpenRouter's `reasoning_details`
round-trip for reasoning models):

```python
from toolloop.providers import OpenRouterProvider

provider = OpenRouterProvider("openai/gpt-4o-mini", reasoning=True)
```

Start with [`examples/`](examples/) — a hands-on tour, from a first offline
agent through hooks, subagents and context management, up to real providers
and applications, including a repository summarizer on
[OpenRouter](examples/repo_summarizer.py).

## Tour

### Defining tools

```python
@tool  # name = function, schema = type hints
async def search_docs(query: str, limit: int = 5) -> str:
    """Search the internal documentation."""
    ...


@tool(dangerous=True)  # flagged for approval hooks
async def run_migration(env: str) -> str:
    """Run the database migration."""
    ...
```

Arguments are validated with pydantic; invalid arguments and raised exceptions
become error observations the model repairs from — they never crash the loop.

### Running agents

```python
result = await agent.run(
    "summarize open PRs",
    max_iterations=25,
    on_max=OnMax.WRAP_UP,  # or RAISE (default) or PARTIAL
    output_model=Summary,  # pydantic model: validated structured output
)
result.status  # Status.COMPLETED | Status.MAX_ITERATIONS
result.output  # str, or a validated Summary instance
result.history  # full audit trail of every step and call
```

### Control modes and hooks

Two modes, configurable on the `Agent` and overridable per `run()`:

- **`ControlMode.BYPASS`** (default) — autonomous; hooks may still veto or
  rewrite calls.
- **`ControlMode.APPROVE`** — default-deny; every tool call must be allowed by
  an `on_tool_call` hook (human-in-the-loop).

```python
async def gatekeeper(ctx) -> Decision:
    if ctx.dangerous:
        answer = input(f"allow {ctx.name}({ctx.args})? [y/N] ")
        return Decision.allow() if answer == "y" else Decision.deny("no")
    return Decision.allow()


agent = Agent(provider, tools=STD_TOOLS, control=ControlMode.APPROVE, on_tool_call=gatekeeper)
```

A ready-made gate is included — `console_approver` allows safe tools silently
and prompts a human only for `dangerous=True` ones:

```python
from toolloop import console_approver

agent = Agent(
    provider, tools=STD_TOOLS, control=ControlMode.APPROVE, on_tool_call=console_approver()
)
```

`on_step` and `on_tool_result` hooks give you full observability (audit,
logging, tracing) in both modes.

### Parallel tool calls

Default is sequential (deterministic). Set `max_parallel_calls` to run the
calls of a single turn concurrently — approvals are still asked one by one,
results are reassembled in the original order:

```python
agent = Agent(provider, tools=[fetch, grep], max_parallel_calls=4)
```

### Streaming (optional, UX-only)

If your provider implements an optional `stream()` method (async iterator of
deltas) and you pass `on_delta`, the agent streams while behaving exactly the
same — the accumulated text is parsed like any other response:

```python
class MyProvider:
    async def complete(self, messages) -> str: ...

    async def stream(self, messages):  # optional
        async for delta in upstream:
            yield delta


agent = Agent(MyProvider(), tools=[...], on_delta=print_delta)
```

### Context management

Set `max_context_tokens` and the agent keeps the conversation within budget:
old tool observations are truncated first, then the middle of the conversation
is compacted via summarization by the provider itself. The standard toolset
already returns compact results by design (a write tool confirms the size it
wrote, it does not echo the content).

```python
agent = Agent(provider, tools=STD_TOOLS, max_context_tokens=16_000)
```

Budgeting uses a ~4-chars-per-token heuristic by default; plug your own
counter (e.g. tiktoken with your model's encoding) with `token_counter=`.

### Session persistence

Snapshot a conversation and resume it later — even in another process. The
state is data (messages + audit trail); provider, tools and hooks are code
and are rebuilt on resume:

```python
state = agent.to_state()
open("session.json", "w").write(state.to_json())  # persist wherever you like

# later:
from toolloop import AgentState

state = AgentState.from_json(open("session.json").read())
agent = Agent.from_state(state, provider, tools=[...])
await agent.run("now, the next step")  # continues the same conversation
```

### Observability

With `opentelemetry` installed (`pip install "toolloop[otel]"`), the loop is
auto-instrumented — spans for `run` → `step` → `tool`, with parse errors as
events. Without the SDK, instrumentation is a no-op and the core carries no
extra dependency. Inject a custom tracer with `Agent(..., tracer=tracer)`.

### Developer logging

The loop logs through the standard `logging` module on the `toolloop` logger.
One line sends it to the terminal or a file — the quickest way to watch an
agent work during development:

```python
from toolloop.devlog import dev_logger

dev_logger()  # -> stderr, live
dev_logger("run.log")  # -> file
```

INFO covers each step, tool calls (name, args, status, duration, result
preview) and run outcomes; parse errors arrive as warnings; raw envelopes are
DEBUG. Since it is stdlib logging, it composes with any handlers and formatters
you already use.

### Subagents

Wrap an agent as a tool: it explores with its own isolated context and only
its final answer comes back.

```python
from toolloop import subagent_tool

researcher = Agent(provider, tools=[search_docs])
agent = Agent(provider, tools=[subagent_tool(researcher), write_file])
```

### Standard toolset (optional)

```python
from toolloop import STD_TOOLS
# bash, read_file, write_file, edit_file, list_files, grep
```

Pure-Python coding-agent toolset; import it or ignore it — the core knows
nothing about it.

### Code intelligence toolset (python · go · java · kotlin)

AST-powered tools on tree-sitter, with a **generic surface**: the language is
detected from the file extension, so one small toolset serves all four.
`spring_endpoints`/`spring_beans` map Spring REST surfaces and beans in
java/kotlin trees.

```python
from toolloop.codetools import CODE_TOOLS  # = STD_TOOLS + AST tools

agent = Agent(provider, tools=CODE_TOOLS)
# symbols(path)          — outline with kinds and line ranges
# find_symbol(name, root, kind=None) — definition sites across files
# references(symbol, root) — identifier occurrences (heuristic)
# imports(path)          — imports/package of a file
# spring_endpoints(root) — GET/POST/... + path + handler
# spring_beans(root)     — @Component/@Service/... + @Bean methods
```

Requires `pip install "toolloop[code]"` (tree-sitter + the four grammars).

`references` is deliberately documented as heuristic — tree-sitter parses, it
does not resolve imports or types. Language servers (hover, precise
go-to-def) are a roadmap item, not a dependency.

### MCP tools (Model Context Protocol)

Expose any MCP server's tools to your agent — the whole MCP ecosystem for
free. Arguments pass through untouched (the server validates them per its own
`inputSchema`, rendered verbatim into the system prompt):

```python
from toolloop.mcp import McpServerConfig, mcp_tools

config = McpServerConfig(command="uvx", args=["mcp-server-fetch"])
# or:  McpServerConfig(url="https://example.com/mcp", headers={...})

async with mcp_tools(config) as tools:  # also accepts a list of configs
    agent = Agent(provider, tools=tools)  # tools are alive only inside the with
    await agent.run("fetch the toolloop README")
```

Requires `pip install "toolloop[mcp]"`. A fully offline example (it spawns
its own MCP server) lives in [`examples/06_mcp_tools.py`](examples/06_mcp_tools.py).

### Sync usage

Scripts without an event loop can use `run_sync`:

```python
from toolloop import run_sync

result = run_sync(agent, "how much is 2 + 3?")
```

### Production hardening

The pieces you want before trusting an agent with real work:

```python
from toolloop import Agent, rate_limited

provider = rate_limited(MyProvider(), concurrency=5, min_interval=0.2)  # shared = global

agent = Agent(
    provider,
    tools=[...],
    max_retries=3,  # transient gateway errors: exponential backoff + jitter
    retry_backoff=0.5,
    provider_timeout=60,  # a hanging provider fails fast instead of forever
    checkpoint="session.json",  # incremental state snapshots (or a callable)
    checkpoint_every=10,  # ...every N steps, plus one at the end of each run
)
```

- **Retries** cover transport failures only; parse errors stay with the
  auto-repair loop, and `CancelledError` is never retried.
- **Checkpoints** survive crashes: resume with `Agent.from_state(
  AgentState.from_json(open("session.json").read()), provider, tools)`.
- **Usage per run**: providers may expose `last_usage()` (the shipped adapters
  do); `RunResult.usage` sums it across the run.
- **Cancellation** is graceful: the conversation is preserved and resumable,
  and the `bash` tool never leaves subprocesses behind.

## Testing your agents

`toolloop.testing` ships deterministic scenario helpers — no LLM, no network,
no flakes:

```python
from toolloop import Agent
from toolloop.testing import ScriptedProvider, final_answer, tool_call


async def test_agent_completes():
    provider = ScriptedProvider(
        [tool_call("search_docs", call_id="c1", query="pypi"), final_answer("done")]
    )
    result = await Agent(provider, tools=[search_docs]).run("search pypi")
    assert result.output == "done"
    assert result.history[0].calls[0].status == "ok"
```

Running out of script fails loudly (`AssertionError`), so scenarios can't
silently drift from what the agent actually does.

## CLI

Scaffold and validate projects (no `run` — it's a library):

```bash
toolloop init my-agent   # full scaffold on an empty folder; on an existing
                         # project, only missing toolloop metadata is added
toolloop check           # validates tools/agent declared in [tool.toolloop]
```

`toolloop init` never overwrites existing files, and the scaffold comes with
an offline scenario test. `python -m toolloop` works too.

## Project

- License: MIT
- Python: 3.11+
- Dependencies: pydantic (only)
- Roadmap: [roadmap.md](roadmap.md) — provider adapters as extras, OpenTelemetry, session persistence, ...

## How it works

1. Tool schemas and the JSON envelope format are rendered into the system
   prompt by a pluggable `ToolProtocol` (default: `JsonToolProtocol`).
2. The agent calls the provider and parses the response envelope:
   `tool_call` (a list of calls, sequential by default or concurrent with
   `max_parallel_calls`) or `final_answer`.
3. Tool results are appended as observations; parse/validation errors are fed
   back so the model can repair its own output.
4. The loop ends on `final_answer`, on `max_iterations` (per the configured
   policy), or when a hook denies everything.
