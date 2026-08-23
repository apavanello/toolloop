# Getting started

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

## Your first agent (no LLM needed)

The quickest way to feel the loop is a scripted provider — pre-written
responses playing the role of a model:

```python
import asyncio

from toolloop import Agent, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


provider = ScriptedProvider(
    [
        tool_call("add", call_id="c1", a=2, b=3),  # the "model" wants a tool
        final_answer("2 + 3 = 5"),  # then it is satisfied
    ]
)
agent = Agent(provider, tools=[add])
result = asyncio.run(agent.run("how much is 2 + 3?"))

print(result.status)  # Status.COMPLETED
print(result.output)  # "2 + 3 = 5"
print(result.history)  # full audit trail of every step and tool call
```

!!! tip
    `toolloop.testing` is also how you write deterministic tests for your own
    agents — see [Testing your agents](#testing-your-agents) below.

## Bring your own provider

The provider contract is **one async method** — SDK, plain HTTP, whatever:

```python
class MyCorporateProxyProvider:
    async def complete(self, messages):
        response = await my_corporate_sdk.chat(
            [{"role": m.role.value, "content": m.content} for m in messages]
        )
        return response.text
```

That is the whole integration. toolloop never manages providers, keys or
models — that stays in your code.

### Ready-made adapters

Tested adapters live in `toolloop.providers`, installed via extras:

```python
from toolloop.providers import OpenRouterProvider

provider = OpenRouterProvider("openai/gpt-4o-mini", reasoning=True)
```

- `OpenAICompatProvider` — any OpenAI-compatible endpoint (OpenAI, Ollama,
  vLLM, corporate proxies)
- `OpenRouterProvider` — OpenRouter, including reasoning models
  (`reasoning=True` preserves `reasoning_details` across turns)
- `AnthropicProvider` — the Anthropic Messages API

## Testing your agents

Because the provider contract is one method, deterministic tests are trivial:

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

Running out of script fails loudly (`AssertionError`), so scenarios cannot
silently drift from what the agent actually does.

## Next steps

- [The agent loop](concepts/loop.md) — what the envelopes look like and how
  the loop decides to stop
- [Tools](concepts/tools.md) — defining your own with `@tool`
- [Examples](examples.md) — nine offline examples you can run right now
