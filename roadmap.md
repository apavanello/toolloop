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

### v1.0.0 — production ready (2026-08)

- **Provider resilience**: `max_retries` + `retry_backoff` (exponential with
  jitter; transport failures only, never cancellation) and
  `provider_timeout` per call.
- **Rate limiting**: `toolloop.resilience.rate_limited(provider,
  concurrency=..., min_interval=...)` — composable wrapper; one instance
  shared across agents is a process-wide limit.
- **Incremental checkpoints**: `checkpoint=` (callable or path) fires every
  `checkpoint_every` steps and at run end; failures never kill the run.
- **Usage per run**: optional `provider.last_usage()` contract; `RunResult
  .usage` sums it (shipped adapters report SDK usage).
- **Graceful cancellation**: conversation preserved and resumable; the `bash`
  tool kills its subprocess.
- **Pipeline**: GitHub repo + CI (matrix 3.11–3.13) + release workflow with
  PyPI trusted publishing (tag `v*` -> tests -> build -> publish).

### Docs site (post-1.0, 2026-08)

- MkDocs Material site (`docs/`) with guides, production notes and an API
  reference generated from docstrings (mkdocstrings); deployed to GitHub
  Pages on every push that touches `docs/`.

### v1.1.0 — code intelligence toolset (2026-08)

- **`toolloop.codetools`** (extra `[code]`, tree-sitter): `symbols`,
  `find_symbol`, `references` (heuristic), `imports` — python/go/java/kotlin
  with a generic surface (language detected by extension). Spring-aware JVM
  tools: `spring_endpoints` (verb+path+handler) and `spring_beans`.
  `CODE_TOOLS` = standard toolset + AST tools.
- `tool_call()` builder parameter renamed to `tool` (positional use
  unchanged) so tools with a `name` argument don't collide.
- Language-server integration (hover, precise go-to-def) deliberately NOT
  included — see candidates below.

## Next up

### v1.2 — candidates

- **Sub-agent orchestration**: typed handoffs, shared registries, teams.
- **Evals as assets**: curated scenario suites (pytest + `toolloop.testing`)
  tracked as repeatable evaluations.
- **ReAct protocol variant**: for models that handle free-text formats better
  than JSON (the protocol seam already exists).
- **Language-server bridge** (LSP): hover/go-to-def/diagnostics — likely via
  the same lifecycle pattern as the MCP bridge.

## Non-goals

- Provider management or SDK bundling in core.
- Being a Claude Code clone: toolloop is a **library for building your own
  harness**, not a product.
