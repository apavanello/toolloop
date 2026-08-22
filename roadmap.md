# toolloop — roadmap

Living document; dates are targets, not promises. Everything here follows the
project's core rule: **the framework never manages providers** — features must
work with any `complete(messages) -> str` implementation.

## Shipped

### v0.1.0 — the loop (2026-08)

- Agent loop: input → tool calls → `final_answer`, with full audit history.
- Pluggable tool protocol; default `JsonToolProtocol` (JSON envelope +
  tolerant parser + auto-repair fed back to the model).
- `@tool` decorator: async functions, schema from type hints, pydantic
  validation, exceptions/invalid args become repair observations.
- Control modes `APPROVE` (default-deny, human-in-the-loop) and `BYPASS`
  (default-allow, hooks can still veto/modify).
- Hooks: `on_step`, `on_tool_call`, `on_tool_result`.
- Context management: truncation of old observations + compaction by
  summarization (`max_context_tokens`).
- `subagent_tool`: agent-as-tool with isolated context (only the final answer
  flows back).
- Standard toolset (optional): `bash`, `read_file`, `write_file`, `edit_file`,
  `list_files`, `grep` — compact results by design.
- `max_iterations` policies: `RAISE` / `WRAP_UP` / `PARTIAL`; structured final
  output via `output_model`.
- 47 deterministic tests (scripted fake provider), reference provider adapters
  in `examples/`.

### v0.2.0 — autonomy, ergonomics, tooling (2026-08)

- **Parallel tool calls**: `max_parallel_calls=N` runs the calls of a turn
  concurrently (`asyncio.gather` + semaphore). Gating (approvals/vetos) is
  always sequential; results and observations keep the original call order.
- **Streaming contract (optional, UX-only)**: providers may implement
  `stream(messages)` (async iterator of deltas); with an `on_delta` callback
  the agent streams while parsing the accumulated text exactly like a
  `complete()` response.
- **`toolloop.testing`**: `ScriptedProvider` + `tool_call()`/`final_answer()`
  envelope builders for deterministic scenario tests.
- **`toolloop.approval`**: `console_approver()` — batteries-included
  human-in-the-loop gate (safe tools silent, dangerous ones prompted).
- **CLI**: `toolloop init` (full scaffold on empty folders; metadata-only on
  existing projects; never overwrites) and `toolloop check` (validates the
  modules declared in `[tool.toolloop]`: imports, duplicate tool names, schema
  rendering). Deliberately **no `run`** — it's a library.

### v0.3.0 — ecosystem & production (2026-08)

- **Providers as tested extras**: `toolloop[openai]` (OpenAICompatProvider +
  OpenRouterProvider, including reasoning models' `extra_body` and the
  `reasoning_details` round-trip) and `toolloop[anthropic]`. Lazy imports with
  helpful errors; SDKs stubbed in the test suite.
- **Session persistence**: `Agent.to_state()` / `Agent.from_state()` /
  `AgentState.to_json()/from_json()` — snapshot and resume conversations
  (provider/tools are code and are rebuilt on resume).
- **OpenTelemetry auto-instrumentation**: span tree `run → step → tool` with
  parse-error events, via lazy import (no-op without the SDK). Extra
  `toolloop[otel]`; custom tracers via `Agent(tracer=...)`.
- **Pluggable token accounting**: `Agent(token_counter=...)` feeds
  `ContextManager`; heuristic default stays; tiktoken left to the user
  (model-dependent).

### v0.3.1 — developer logging (2026-08)

- **stdlib logging in the loop**: steps, tool calls (name/args/status/duration)
  and run outcomes at INFO, parse errors as WARNING, raw envelopes at DEBUG —
  on the `toolloop` logger.
- **`toolloop.devlog`**: `dev_logger()` (stderr) / `dev_logger("run.log")`
  (file), idempotent one-liner for dev runs.

### v0.4.0 — MCP bridge + sync facade (2026-08)

- **`toolloop.mcp`**: expose MCP servers as toolloop tools. `mcp_tools()`
  context manager opens stdio or streamable-HTTP transports (official SDK
  helpers), discovers tools and yields `ToolDefinition`s; multiple servers
  with optional name prefixes. Arguments are pass-through — the server's
  `inputSchema` is rendered verbatim into the system prompt and validation
  stays server-side (`ToolDefinition.schema` override added to the core).
  Extra: `toolloop[mcp]`.
- **`toolloop.sync`**: `run_sync(agent, input)` — thin facade for sync code.
- Integration-tested against a real FastMCP server over stdio (subprocess),
  plus fake-session unit tests.

## Next up

### v0.5 — candidates

- **Sub-agent orchestration**: typed handoffs, shared registries, teams.
- **Evals as assets**: curated scenario suites (pytest + `toolloop.testing`)
  tracked as repeatable evaluations.
- **ReAct protocol variant**: for models that handle free-text formats better
  than JSON (the protocol seam already exists).

## Non-goals

- Provider management or SDK bundling in core.
- Being a Claude Code clone: toolloop is a **library for building your own
  harness**, not a product.
