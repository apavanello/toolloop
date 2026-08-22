"""Provider adapter for the Anthropic Messages API.

Install the SDK with: pip install anthropic
"""

from __future__ import annotations

from anthropic import AsyncAnthropic

from toolloop import Message


class AnthropicProvider:
    """Implements toolloop's one-method provider contract."""

    def __init__(self, model: str = "claude-sonnet-4-5", max_tokens: int = 4096) -> None:
        self.client = AsyncAnthropic()
        self.model = model
        self.max_tokens = max_tokens

    async def complete(self, messages: list[Message]) -> str:
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
        return "".join(block.text for block in response.content if block.type == "text")
