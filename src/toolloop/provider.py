"""The minimal provider contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ._types import Message


class Provider(Protocol):
    """Any async text-in/text-out LLM endpoint.

    Implement this with your SDK of choice (or plain HTTP) and pass it to
    :class:`toolloop.Agent`. No tool-use support is required or expected —
    that is the whole point of the framework.
    """

    async def complete(self, messages: Sequence[Message]) -> str:
        """Render ``messages`` and return the model's text response."""
        ...
