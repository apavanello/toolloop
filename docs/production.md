# Production

The pieces you want before trusting an agent with real work.

## The full posture

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

## Retries & timeout

`max_retries` + `retry_backoff` retry transport failures (network blips, 5xx,
timeouts) with exponential backoff and jitter (capped at 30s). The rules:

- `asyncio.CancelledError` is **never** retried — cancellation propagates.
- Parse errors are not retried — [auto-repair](concepts/loop.md) owns them.
- `provider_timeout` wraps each attempt; a hanging provider raises
  `TimeoutError` in `provider_timeout` seconds instead of forever.

## Rate limiting

`rate_limited()` wraps any provider with a concurrency cap and/or a minimum
interval between calls. One wrapper **shared across agents** is a
process-wide limit:

```python
from toolloop import rate_limited

limited = rate_limited(MyProvider(), concurrency=5, min_interval=0.2)
agent_a = Agent(limited, tools=[...])
agent_b = Agent(limited, tools=[...])  # both share the budget
```

`stream` and `last_usage` pass through when the inner provider has them.

## Usage per run

Providers may expose `last_usage()` — whatever the SDK reports (tokens, cost).
`RunResult.usage` sums numeric leaves across the run; it is `None` when the
provider does not report:

```python
result = await agent.run("x")
result.usage  # {"prompt_tokens": 200, "completion_tokens": 80, "model": "demo"}
```

The shipped adapters implement `last_usage()` from their SDKs.

## Observability — OpenTelemetry

With the SDK installed (`pip install "toolloop[otel]"`), the loop is
auto-instrumented — spans for `toolloop.run` → `toolloop.step` →
`toolloop.tool`, with parse errors as events and durations as attributes.
Without the SDK, instrumentation is a no-op: the core never imports
opentelemetry directly. Custom tracer: `Agent(..., tracer=tracer)`.

## Developer logging

One line sends the loop's stdlib logging to the terminal or a file:

```python
from toolloop.devlog import dev_logger

dev_logger()  # -> stderr, live
dev_logger("run.log")  # -> file
```

INFO covers steps, tool calls (name, args, status, duration, result preview)
and run outcomes; parse errors are warnings; raw envelopes are DEBUG. It
composes with any stdlib handlers you already use.

## Sync facade

```python
from toolloop import run_sync

result = run_sync(agent, "how much is 2 + 3?")
```

`run_sync` spawns its own event loop; inside a running loop it raises a clear
error (use `await agent.run(...)` there).
