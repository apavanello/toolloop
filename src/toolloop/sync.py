"""A thin sync facade over the async API."""

from __future__ import annotations

import asyncio
from typing import Any

from .agent import Agent, RunResult


def run_sync(agent: Agent, input: str, **kwargs: Any) -> RunResult:
    """Run an agent from sync code (spawns its own event loop).

    Cannot be used from inside a running event loop — ``await agent.run(...)``
    directly there.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(agent.run(input, **kwargs))
    raise RuntimeError(
        "run_sync() cannot be called from a running event loop; await agent.run(...) directly"
    )
