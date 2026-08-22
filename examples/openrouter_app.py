"""A simple application: a repository summarizer agent on OpenRouter.

Usage:
    OPENROUTER_API_KEY=sk-or-... uv run --with openai python \
        examples/openrouter_app.py [path]

The agent explores a codebase with tools (one custom + three from the
standard toolset), logs its progress through an on_step hook, and returns a
structured summary validated by pydantic — no native tool use required from
the provider.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from openrouter_provider import OpenRouterProvider
from pydantic import BaseModel

from toolloop import Agent, ControlMode, OnMax, Status, tool
from toolloop.tools import grep, list_files, read_file


class RepoSummary(BaseModel):
    """Structured output the agent must produce."""

    description: str
    languages: list[str]
    entry_points: list[str]


@tool
async def file_tree(path: str = ".") -> str:
    """One-level overview of a directory: entries with per-directory file counts."""
    root = Path(path)
    lines = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            count = sum(1 for item in entry.rglob("*") if item.is_file())
            lines.append(f"{entry.name}/ ({count} files)")
        else:
            lines.append(entry.name)
    return "\n".join(lines) or "(empty)"


async def log_progress(ctx) -> None:
    """on_step hook: cheap console observability."""
    if ctx.kind == "tool_calls":
        calls = ", ".join(f"{call.name}({call.status})" for call in ctx.calls)
        print(f"  step {ctx.step}: {calls}")


async def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    provider = OpenRouterProvider(
        model=os.environ.get("TOOLLOOP_MODEL", "openai/gpt-4o-mini")
    )
    agent = Agent(
        provider,
        tools=[file_tree, list_files, read_file, grep],
        control=ControlMode.BYPASS,
        on_step=log_progress,
        system_prompt=(
            "You are a codebase analyst. Explore the target directory with the "
            "tools, read what matters, then produce an honest, concise summary. "
            "Do not invent facts you did not observe."
        ),
        max_context_tokens=16_000,
    )
    result = await agent.run(
        f"Analyze the repository at {target!r} and summarize it.",
        max_iterations=20,
        on_max=OnMax.WRAP_UP,
        output_model=RepoSummary,
    )
    if result.status is not Status.COMPLETED:
        print("agent did not complete:", result.status.value)
        sys.exit(1)

    summary: RepoSummary = result.output
    print("\n== repository summary ==")
    print("description  :", summary.description)
    print("languages    :", ", ".join(summary.languages))
    print("entry points :", ", ".join(summary.entry_points))
    total_calls = sum(len(step.calls) for step in result.history)
    print(f"\n({len(result.history)} steps, {total_calls} tool calls)")


if __name__ == "__main__":
    asyncio.run(main())
