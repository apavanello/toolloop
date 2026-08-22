# Sessions & checkpoints

Long-lived agents need to survive restarts, and long runs need to survive
crashes. Both are state — data — while provider, tools and hooks remain code.

## Save and resume a conversation

```python
state = agent.to_state()                      # messages + audit history
open("session.json", "w").write(state.to_json())   # persist anywhere

# later — even in another process:
from toolloop import Agent, AgentState

state = AgentState.from_json(open("session.json").read())
agent = Agent.from_state(state, provider, tools=[...])
await agent.run("now, the next step")   # continues the SAME conversation
```

The next `run()` appends its input to the loaded conversation; the audit
history accumulates across the session. `AgentState` is versioned —
`from_json` rejects unknown versions.

!!! warning
    If the tool set changed between save and resume, the mismatch with the
    system prompt stored in the messages is your responsibility.

## Incremental checkpoints

`checkpoint=` fires every `checkpoint_every` steps **and once at the end of
each run** — so a crashed run loses at most N steps:

```python
agent = Agent(
    provider,
    tools=[...],
    checkpoint="session.json",   # or any Callable[[AgentState], Any]
    checkpoint_every=10,
)
```

Callable checkpoints can be async, and a failing checkpoint **never kills
the run** (it is logged and ignored).

## Graceful cancellation

Cancelling a run (Ctrl+C, shutdown) preserves the conversation — the `finally`
in the loop stores it — so `from_state` + `run()` picks up exactly where the
agent was interrupted. The `bash` tool kills its subprocess on cancellation;
nothing is left behind.

## Subagents

`subagent_tool` wraps an Agent as a tool: it explores with its **own isolated
context** and only its final answer flows back to the caller — the a2a-style
"trust the sub-execution" pattern for greedy exploration without polluting
the main context.

```python
from toolloop import subagent_tool

researcher = Agent(provider, tools=[search_docs])
agent = Agent(provider, tools=[subagent_tool(researcher), write_file])
```
