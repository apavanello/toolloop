"""Provider adapter for the Anthropic Messages API.

Requires the anthropic SDK: ``pip install "toolloop[anthropic]"``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from anthropic import AsyncAnthropic

from .. import Message


class AnthropicProvider:
    """Implements toolloop's one-method provider contract."""

    def __init__(self, model: str = "claude-sonnet-4-5", max_tokens: int = 4096) -> None:
        self.client = AsyncAnthropic()
        self.model = model
        self.max_tokens = max_tokens
        self._last_usage: dict[str, Any] | None = None

    async def complete(self, messages: Sequence[Message]) -> str:
        system = "\n\n".join(m.content for m in messages if m.role.value == "system")
        conversation = [
            {
                "role": "assistant" if m.role.value == "assistant" else "user",
                "content": m.content,
            }
            for m in messages
            if m.role.value != "system"
        ]
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=conversation,
        )
        usage = getattr(response, "usage", None)
        self._last_usage = usage.model_dump() if usage else None
        return "".join(block.text for block in response.content if block.type == "text")

    def last_usage(self) -> dict[str, Any] | None:
        """Usage of the last response as reported by the SDK (tokens, etc.)."""
        return self._last_usage
