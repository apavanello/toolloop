"""Provider adapter for OpenRouter (OpenAI-compatible API).

Keys: https://openrouter.ai/keys — export OPENROUTER_API_KEY.
Model names use OpenRouter's ``provider/model`` format, e.g.
``openai/gpt-4o-mini`` or ``anthropic/claude-sonnet-4.5``.

Install the SDK with: pip install openai
"""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from toolloop import Message


class OpenRouterProvider:
    """Implements toolloop's one-method provider contract via OpenRouter."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.client = AsyncOpenAI(
            base_url=self.BASE_URL,
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
            default_headers={"X-Title": "toolloop example"},
        )
        self.model = model

    async def complete(self, messages: list[Message]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
        )
        return response.choices[0].message.content or ""
