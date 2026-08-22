"""Provider adapter for OpenRouter, built on the official OpenAI SDK.

Keys: https://openrouter.ai/keys — export ``OPENROUTER_API_KEY``. Model names
use OpenRouter's ``provider/model`` format, e.g. ``openai/gpt-4o-mini``.

Reasoning models (e.g. ``stealth/ox-alpha``): pass ``reasoning=True`` to send
``extra_body={"reasoning": {"enabled": True}}``, exactly like OpenRouter's
docs. The adapter also preserves ``reasoning_details`` on assistant messages
across turns ("pass back unmodified"), so the model keeps its chain of
thought between tool-call rounds.

Requires the openai SDK: ``pip install "toolloop[openai]"``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI

from .. import Message


class OpenRouterProvider:
    """Implements toolloop's one-method provider contract via OpenRouter."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        *,
        extra_body: dict[str, Any] | None = None,
        reasoning: bool = False,
    ) -> None:
        self.client = AsyncOpenAI(
            base_url=self.BASE_URL,
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
            default_headers={"X-Title": "toolloop"},
        )
        self.model = model
        merged = dict(extra_body or {})
        if reasoning:
            merged.setdefault("reasoning", {"enabled": True})
        self.extra_body = merged or None
        # reasoning_details of each assistant turn, keyed by a content prefix
        # so they can be replayed ("passed back unmodified") on later calls.
        self._reasoning_by_prefix: dict[str, Any] = {}

    async def complete(self, messages: Sequence[Message]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self._build_payload(messages),
            extra_body=self.extra_body,
        )
        message = response.choices[0].message
        details = getattr(message, "reasoning_details", None)
        if details is not None and message.content:
            self._reasoning_by_prefix[message.content[:64]] = details
        return message.content or ""

    def _build_payload(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for message in messages:
            entry: dict[str, Any] = {"role": message.role.value, "content": message.content}
            if message.role.value == "assistant":
                details = self._reasoning_by_prefix.get(message.content[:64])
                if details is not None:
                    entry["reasoning_details"] = details
            payload.append(entry)
        return payload
