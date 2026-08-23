"""Deterministic testing helpers: scripted providers and envelope builders.

Scenario tests with these helpers run without an LLM, without network and
without flakes — see the repository tests for real usage.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ._types import Message


class ScriptedProvider:
    """Provider with pre-written responses; records every call it receives.

    Responses are consumed in order, one per ``complete()`` call. Running out
    of script raises ``AssertionError`` — a failing-by-default signal that
    your scenario expectations drifted from the agent's actual behavior.
    """

    def __init__(self, responses: Sequence[str]):
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError(
                f"ScriptedProvider ran out of scripted responses after {len(self.calls)} calls"
            )
        return self.responses.pop(0)


def tool_call(tool: str, call_id: str | None = None, **args: Any) -> str:
    """Envelope string requesting a single tool call.

    ``tool`` is positional on purpose: the keyword arguments are the tool's
    own arguments (which may legitimately be called ``name``).
    """
    entry: dict[str, Any] = {"name": tool, "args": args}
    if call_id is not None:
        entry["id"] = call_id
    return json.dumps({"type": "tool_call", "calls": [entry]})


def final_answer(output: Any) -> str:
    """Envelope string delivering a final answer."""
    return json.dumps({"type": "final_answer", "output": output})
