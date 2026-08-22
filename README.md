# toolloop

**Agent loops for LLM providers without native tool use.**

`toolloop` is a Python framework for building autonomous agents — tool use,
exploration, coding — on top of any LLM endpoint, even (especially) the ones
whose SDKs never exposed a `tools` parameter. If you can send messages and get
text back, you can run an agent on it.

```
             ┌─────────────────────────────────────────────┐
             │                                             │
  input ──▶  │   system prompt (tool instructions)        │
             │   + conversation history                    │
             ▼                                             │
       ┌───────────┐   {"type":"tool_call", ...}   ┌────────────┐
       │ provider  │ ────────────────────────────▶ │ tool runs  │
       │ (yours)   │                               └────────────┘
       └───────────┘                                       │
             │                                             │ observation
             │ {"type":"final_answer", ...}               ▼
             ▼                                       back to provider
          output
```

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
pip install toolloop        # once published
# or, from source:
uv sync --extra dev
```

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
print(result.output)                    # 2 + 3 = 5
print(result.status)                    # Status.COMPLETED
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

Reference adapters (OpenAI-compatible endpoints and Anthropic) live in
[`examples/`](examples/) as copy-paste code, not dependencies.

## Tour

### Defining tools

```python
@tool                                    # name = function, schema = type hints
async def search_docs(query: str, limit: int = 5) -> str:
    """Search the internal documentation."""
    ...

@tool(dangerous=True)                    # flagged for approval hooks
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
    on_max=OnMax.WRAP_UP,       # or RAISE (default) or PARTIAL
    output_model=Summary,       # pydantic model: validated structured output
)
result.status                   # Status.COMPLETED | Status.MAX_ITERATIONS
result.output                   # str, or a validated Summary instance
result.history                  # full audit trail of every step and call
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

`on_step` and `on_tool_result` hooks give you full observability (audit,
logging, tracing) in both modes.

### Context management

Set `max_context_tokens` and the agent keeps the conversation within budget:
old tool observations are truncated first, then the middle of the conversation
is compacted via summarization by the provider itself. The standard toolset
already returns compact results by design (a write tool confirms the size it
wrote, it does not echo the content).

```python
agent = Agent(provider, tools=STD_TOOLS, max_context_tokens=16_000)
```

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

## Testing your agents

The provider contract is one method, so deterministic tests are trivial:
script a fake provider with canned responses (see `tests/conftest.py` in this
repo) and assert on `result.history` — no LLM, no flakes.

## Project

- License: MIT
- Python: 3.11+
- Dependencies: pydantic (only)
- Roadmap: streaming, parallel tool calls, a small CLI (`init`, `test`), ...

## How it works

1. Tool schemas and the JSON envelope format are rendered into the system
   prompt by a pluggable `ToolProtocol` (default: `JsonToolProtocol`).
2. The agent calls the provider and parses the response envelope:
   `tool_call` (a list of calls, executed sequentially in v1) or
   `final_answer`.
3. Tool results are appended as observations; parse/validation errors are fed
   back so the model can repair its own output.
4. The loop ends on `final_answer`, on `max_iterations` (per the configured
   policy), or when a hook denies everything.
