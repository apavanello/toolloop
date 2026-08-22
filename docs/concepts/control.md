# Control & hooks

Two control modes decide who may run tool calls, and three hooks give you
observability and intervention points.

## Control modes

- **`ControlMode.BYPASS`** (default) — autonomous. Hooks may still veto or
  rewrite any call; returning `None` means "default-allow".
- **`ControlMode.APPROVE`** — default-deny. Every tool call must receive an
  explicit `Decision.allow()` from an `on_tool_call` hook (your
  human-in-the-loop point). Using APPROVE without an `on_tool_call` hook
  fails fast with `ControlError`.

Modes are set on the `Agent` and overridable per `run()`:

```python
agent = Agent(provider, tools=[...], control=ControlMode.APPROVE)
await agent.run("x", control=ControlMode.BYPASS)  # one-off override
```

## Hooks

| Hook | When | Powers |
| --- | --- | --- |
| `on_step` | after each provider turn | audit, logging, tracing |
| `on_tool_call` | before each tool executes | veto, rewrite args, ask a human |
| `on_tool_result` | after each tool completes | metrics, logging |

```python
from toolloop import Decision


async def gatekeeper(ctx) -> Decision:
    if ctx.dangerous:
        answer = input(f"allow {ctx.name}({ctx.args})? [y/N] ")
        return Decision.allow() if answer == "y" else Decision.deny("no")
    return Decision.allow()


agent = Agent(
    provider,
    tools=STD_TOOLS,
    control=ControlMode.APPROVE,
    on_tool_call=gatekeeper,
)
```

Hooks can also **rewrite arguments** before execution:

```python
return Decision.allow(args={**ctx.args, "env": "staging"})
```

## console_approver — batteries included

```python
from toolloop import console_approver

agent = Agent(
    provider,
    tools=STD_TOOLS,
    control=ControlMode.APPROVE,
    on_tool_call=console_approver(),  # prompt is injectable for tests
)
```

Safe tools pass silently; `dangerous=True` tools get a terminal prompt.

!!! note
    Observability hooks (`on_step`, `on_tool_result`) fire in both modes —
    including BYPASS. Only the gating default changes.
