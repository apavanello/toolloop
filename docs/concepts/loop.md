# The agent loop

The loop is the heart of toolloop: given an input, the agent talks to the
provider, parses tool calls out of plain text, runs the tools, feeds results
back as observations, and repeats until the model emits a final answer.

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

## The JSON envelope

The protocol (pluggable — see below) teaches the model to answer with one of
two envelopes:

```json
{"type": "tool_call", "calls": [{"id": "c1", "name": "fetch", "args": {"url": "..."}}]}
{"type": "final_answer", "output": "here is what I found"}
```

The loop terminates **only** on `final_answer`. Parsing is tolerant: fenced
code blocks (last valid block wins) or bare JSON, with or without surrounding
prose.

## Auto-repair

When the response cannot be parsed — or a tool's arguments fail validation —
the error is fed back to the model as an observation:

```
Your last response could not be parsed: envelope must be a JSON object...
Respond again with a single JSON envelope (tool_call or final_answer).
```

The model fixes its own output on the next turn. Invalid arguments and raised
exceptions never crash the loop; `max_parse_failures` (default 3) bounds the
repair attempts.

!!! note
    Parse errors are model behavior and are **not** retried by the production
    retry policy — auto-repair owns them. Transport failures (network, 5xx)
    are the ones retried; see [Production](../production.md).

## Stop conditions and budgets

- **`max_iterations`** (default 25) bounds the number of provider calls per
  run. When exhausted, `on_max` decides:
    - `OnMax.RAISE` — raise `MaxIterationsExceeded` (default)
    - `OnMax.WRAP_UP` — one forced extra turn: "answer now"
    - `OnMax.PARTIAL` — return `RunResult(status=MAX_ITERATIONS)`
- **Structured output** — pass a pydantic model and the `final_answer`
  payload is validated against it (invalid output goes back for repair too):

```python
class Summary(BaseModel):
    answer: str
    citations: list[str]

result = await agent.run("summarize", output_model=Summary)
result.output  # a validated Summary instance
```

## Pluggable protocols

The default `JsonToolProtocol` renders tool schemas into the system prompt and
parses the envelope above. The seam is a two-method interface —
`render_instructions()` + `parse()` — so alternative formats (ReAct, XML tags,
...) can be swapped in:

```python
agent = Agent(provider, tools=[...], protocol=MyProtocol())
```

## The audit trail

`RunResult.history` records every step: raw responses, parsed kinds
(`tool_calls` / `final_answer` / `parse_error`), tool call records with
status, duration and result. It is also what the [hooks](control.md) receive
and what ends up in [session state](sessions.md).
