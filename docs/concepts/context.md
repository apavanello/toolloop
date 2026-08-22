# Context window

Agent loops accumulate tokens fast: every tool result enters the history.
`max_context_tokens` keeps the conversation within a budget in two stages,
cheapest first.

## Stage 1 — truncation

The **oldest tool observations** are cut down to a short preview (the two
most recent stay whole). System prompt and recent turns are never touched.

## Stage 2 — compaction

Still over budget? The middle of the conversation is summarized **by the
provider itself**; the summary replaces it. The system prompt and the most
recent messages are always preserved.

```python
agent = Agent(
    provider,
    tools=STD_TOOLS,
    max_context_tokens=16_000,
)
```

## Pluggable token counter

Budgeting uses a ~4-chars-per-token heuristic by default. Plug your own
counter — e.g. tiktoken with your model's encoding:

```python
agent = Agent(
    provider,
    tools=STD_TOOLS,
    max_context_tokens=16_000,
    token_counter=my_counter,  # Callable[[Sequence[Message]], int]
)
```

## Compact results by design

The standard toolset already cooperates: `write_file` confirms the size it
wrote instead of echoing the content, reads are capped, and a per-result
safety net (`max_tool_result_chars`) truncates anything a tool returns that
is too large — with a notice to the model.

!!! tip
    For heavy exploration (read many files, grep everywhere), delegate to a
    [subagent](sessions.md) — it explores in its own context window and only
    its final answer flows back.
