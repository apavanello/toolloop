"""Shared test doubles."""

from __future__ import annotations

from toolloop._types import Message


class FakeProvider:
    """Scripted provider: pops responses in order and records every call."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    async def complete(self, messages) -> str:
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("FakeProvider ran out of scripted responses")
        return self.responses.pop(0)
