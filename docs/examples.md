# Examples

Nine numbered examples — **all runnable offline** with scripted providers —
plus two applications that need real providers.

Run any of them from the repository root:

```bash
git clone https://github.com/apavanello/toolloop && cd toolloop
uv sync --extra dev
uv run python examples/01_first_agent.py
```

## The guided tour

| # | Example | You will learn |
| --- | --- | --- |
| 01 | [`01_first_agent.py`](https://github.com/apavanello/toolloop/blob/main/examples/01_first_agent.py) | the three moving parts: provider, tools, agent loop |
| 02 | [`02_custom_tools.py`](https://github.com/apavanello/toolloop/blob/main/examples/02_custom_tools.py) | `@tool`, pydantic validation, the auto-repair loop |
| 03 | [`03_control_and_hooks.py`](https://github.com/apavanello/toolloop/blob/main/examples/03_control_and_hooks.py) | `APPROVE` vs `BYPASS`, deny/rewrite calls, observability |
| 04 | [`04_subagent.py`](https://github.com/apavanello/toolloop/blob/main/examples/04_subagent.py) | delegation with an isolated context |
| 05 | [`05_context_window.py`](https://github.com/apavanello/toolloop/blob/main/examples/05_context_window.py) | truncation + compaction, pluggable `token_counter` |
| 06 | [`06_mcp_tools.py`](https://github.com/apavanello/toolloop/blob/main/examples/06_mcp_tools.py) | MCP servers as tools (spawns its own server — offline) |
| 07 | [`07_parallel_and_streaming.py`](https://github.com/apavanello/toolloop/blob/main/examples/07_parallel_and_streaming.py) | `max_parallel_calls` wall-clock, `stream()` + `on_delta` |
| 08 | [`08_sessions_and_checkpoints.py`](https://github.com/apavanello/toolloop/blob/main/examples/08_sessions_and_checkpoints.py) | save/resume a conversation, incremental checkpoints |
| 09 | [`09_production_hardening.py`](https://github.com/apavanello/toolloop/blob/main/examples/09_production_hardening.py) | retries, timeout, rate limiting, usage, `run_sync` — all sync |

## Applications

- **`coding_agent.py`** — a minimal coding harness: standard toolset,
  `ControlMode.APPROVE` with `console_approver`, dev logging,
  retries/timeout and a crash-resume checkpoint.

  ```bash
  OPENAI_API_KEY=... uv run --extra openai python examples/coding_agent.py "task"
  ```

- **`repo_summarizer.py`** — a repository summarizer on OpenRouter with a
  custom tool, an `on_step` progress hook and structured output validated by
  pydantic.

  ```bash
  OPENROUTER_API_KEY=sk-or-... uv run --extra openai python examples/repo_summarizer.py .
  ```
