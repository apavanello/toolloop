"""Provider adapter for any OpenAI-compatible Chat Completions endpoint.

Works with OpenAI itself or any compatible gateway (Ollama, vLLM, corporate
proxies...). Install the SDK with: pip install openai
"""

from __future__ import annotations

from openai import AsyncOpenAI

from toolloop import Message


class OpenAICompatProvider:
    """Implements toolloop's one-method provider contract."""

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def complete(self, messages: list[Message]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
        )
        return response.choices[0].message.content or ""
