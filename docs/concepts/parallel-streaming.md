# Parallel & streaming

## Parallel tool calls

The default is sequential — deterministic. Set `max_parallel_calls` to run
the calls of a single turn concurrently:

```python
agent = Agent(provider, tools=[fetch, grep], max_parallel_calls=4)
```

Two guarantees hold either way:

- **Gating stays sequential** — approvals/vetoes are asked one by one, so a
  human is never presented two questions at once.
- **Results keep the original call order** — observations and the audit
  history are identical to a sequential run; only the clock changes.

```text
sequential (default)      0.90s
max_parallel_calls=3      0.30s   (three 0.3s tools, concurrent)
```

A semaphore caps concurrency; `on_tool_result` fires as each call finishes.

## Streaming (optional, UX-only)

Providers may implement an optional `stream()` method — an async iterator of
deltas. With an `on_delta` callback configured, the agent streams while
behaving exactly the same: the accumulated text is parsed like any other
response.

```python
class MyProvider:
    async def complete(self, messages) -> str: ...

    async def stream(self, messages):  # optional
        async for delta in upstream:
            yield delta


agent = Agent(MyProvider(), tools=[...], on_delta=lambda d: print(d, end=""))
```

Without `on_delta`, or on providers without `stream()`, the loop uses
`complete()` — there is no behavioral difference, only latency to first
token.
