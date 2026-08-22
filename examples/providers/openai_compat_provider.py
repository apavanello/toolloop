"""Provider adapter for any OpenAI-compatible Chat Completions endpoint.

Works with OpenAI itself or any compatible gateway (Ollama, vLLM, corporate
proxies...). Install the SDK with: pip install openai
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI

from toolloop import Message


class OpenAICompatProvider:
    """Implements toolloop's one-method provider contract."""

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.extra_body = extra_body

    async def complete(self, messages: Sequence[Message]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
            extra_body=self.extra_body,
        )
        return response.choices[0].message.content or ""
