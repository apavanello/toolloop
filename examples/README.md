# toolloop by example

A hands-on tour. **Start at 01 and walk down** — every numbered example runs
offline with a scripted provider: no API key, no SDK, no cost. Real providers
and applications come last.

| order | example | you will learn |
| --- | --- | --- |
| 01 | [`01_first_agent.py`](01_first_agent.py) | the three moving parts: provider, tools, agent loop |
| 02 | [`02_custom_tools.py`](02_custom_tools.py) | `@tool`, pydantic validation, the auto-repair loop |
| 03 | [`03_control_and_hooks.py`](03_control_and_hooks.py) | `APPROVE` vs `BYPASS`, deny/rewrite calls, observability |
| 04 | [`04_subagent.py`](04_subagent.py) | delegation with an isolated context |
| 05 | [`05_context_window.py`](05_context_window.py) | truncation + compaction of old observations |

Run any of them from the repository root:

```bash
uv run python examples/01_first_agent.py
```

To test **your own** agents the same deterministic way, use `toolloop.testing`
(`ScriptedProvider` + `tool_call()`/`final_answer()` builders) — see the
"Testing your agents" section of the main README.

## Real providers

Ready-made, tested adapters live in the library itself —
`toolloop.providers` — installed via extras:

```bash
pip install "toolloop[openai]"      # OpenAICompatProvider + OpenRouterProvider
pip install "toolloop[anthropic]"   # AnthropicProvider
```

- `OpenAICompatProvider` — any OpenAI-compatible endpoint (OpenAI, Ollama,
  vLLM, corporate proxies...)
- `OpenRouterProvider` — OpenRouter, including reasoning models
  (`reasoning=True` preserves `reasoning_details` across turns)
- `AnthropicProvider` — the Anthropic Messages API

## Applications

- [`coding_agent.py`](coding_agent.py) — a minimal coding harness: standard
  toolset, `ControlMode.APPROVE`, human gate on dangerous tools.
  ```bash
  OPENAI_API_KEY=... uv run --extra openai python examples/coding_agent.py "task"
  ```
- [`repo_summarizer.py`](repo_summarizer.py) — the mini application: a
  repository summarizer on OpenRouter with a custom tool, an `on_step` progress
  hook and structured output validated by pydantic.
  ```bash
  OPENROUTER_API_KEY=sk-or-... uv run --extra openai python examples/repo_summarizer.py .
  ```

Run the applications from the repository root.
