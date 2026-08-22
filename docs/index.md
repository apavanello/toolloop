# toolloop

**Agent loops for LLM providers without native tool use.**

<p align="center">
  <img src="assets/hero.svg" width="100%"
       alt="toolloop — agent loops for LLM providers without native tool use. Terminal panel showing a real agent run.">
</p>

`toolloop` is a Python framework for building autonomous agents — tool use,
exploration, coding — on top of **any** LLM endpoint, even (especially) the
ones whose SDK never exposed a `tools` parameter. If you can send messages and
get text back, you can run an agent on it.

## Why it exists

Plenty of real-world LLM access goes through proprietary corporate SDKs that
proxy the big providers (Anthropic, OpenAI, Kimi, DeepSeek, ...) but strip or
never implemented the tool-use layer. The models behind them are perfectly
capable of agentic work — the SDK just won't carry function calls.

toolloop solves this at the application layer:

- **Bring your own provider.** The framework never manages providers. The
  whole contract is one async method: `complete(messages) -> str`.
- **Tools over plain text.** Tool schemas are rendered into the system prompt;
  tool calls are parsed out of the model's text responses. Parse errors are
  fed back to the model (auto-repair) until the envelope is right.
- **Loop until satisfied.** Given an input, the agent calls tools, receives
  observations, and iterates until it emits a `final_answer`.

## A taste

```python
import asyncio

from toolloop import Agent, tool


@tool
async def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class DemoProvider:  # scripted: stands in for your real provider
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
```

Runs offline, with zero API keys — start in [Getting started](getting-started.md).

## Where to go next

- [Getting started](getting-started.md) — install, first agent, first provider
- [The agent loop](concepts/loop.md) — envelopes, auto-repair, stop conditions
- [Production](production.md) — retries, rate limiting, checkpoints, observability
- [Examples](examples.md) — nine runnable, offline examples and two full apps
