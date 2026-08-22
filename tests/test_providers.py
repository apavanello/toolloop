from __future__ import annotations

import types
from typing import Any

import pytest

from toolloop import Message, Role
from toolloop.providers import AnthropicProvider, OpenAICompatProvider, OpenRouterProvider


class FakeAsyncOpenAI:
    """Stands in for openai.AsyncOpenAI: records create() calls, replays a script."""

    def __init__(self, **constructor_kwargs: Any):
        self.constructor_kwargs = constructor_kwargs
        self.create_calls: list[dict] = []
        self.script: list[dict] = []
        completions = types.SimpleNamespace(create=self._create)
        self.chat = types.SimpleNamespace(completions=completions)

    async def _create(self, **kwargs: Any) -> Any:
        self.create_calls.append(kwargs)
        reply = self.script.pop(0)
        message = types.SimpleNamespace(
            content=reply.get("content", ""),
            reasoning_details=reply.get("reasoning_details"),
        )
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class FakeAsyncAnthropic:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []
        self.script: list[str] = []
        self.messages = types.SimpleNamespace(create=self._create)

    async def _create(self, **kwargs: Any) -> Any:
        self.create_calls.append(kwargs)
        block = types.SimpleNamespace(type="text", text=self.script.pop(0))
        return types.SimpleNamespace(content=[block])


async def test_openai_compat_maps_roles_and_extra_body():
    provider = OpenAICompatProvider("m1", api_key="sk-test", extra_body={"foo": 1})
    fake = FakeAsyncOpenAI()
    provider.client = fake
    fake.script = [{"content": "hello"}]

    out = await provider.complete([Message(Role.USER, "hi"), Message(Role.ASSISTANT, "ho")])

    assert out == "hello"
    call = fake.create_calls[0]
    assert call["model"] == "m1"
    assert call["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ho"},
    ]
    assert call["extra_body"] == {"foo": 1}


def test_openrouter_constructor_wiring(monkeypatch):
    monkeypatch.setattr("toolloop.providers.openrouter.AsyncOpenAI", FakeAsyncOpenAI)
    provider = OpenRouterProvider("m", api_key="sk-or-test", reasoning=True)
    fake = provider.client

    assert isinstance(fake, FakeAsyncOpenAI)
    assert fake.constructor_kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert fake.constructor_kwargs["default_headers"] == {"X-Title": "toolloop"}
    assert provider.extra_body == {"reasoning": {"enabled": True}}


def test_openrouter_extra_body_merges_with_reasoning():
    provider = OpenRouterProvider("m", api_key="k", extra_body={"top_k": 2}, reasoning=True)
    assert provider.extra_body == {"top_k": 2, "reasoning": {"enabled": True}}


async def test_openrouter_reasoning_details_round_trip():
    provider = OpenRouterProvider("m", api_key="k", reasoning=True)
    fake = FakeAsyncOpenAI()
    provider.client = fake
    fake.script = [
        {"content": "answer-1", "reasoning_details": [{"type": "reasoning", "text": "think"}]},
        {"content": "answer-2"},
    ]

    assert await provider.complete([Message(Role.USER, "q1")]) == "answer-1"
    conversation = [
        Message(Role.USER, "q1"),
        Message(Role.ASSISTANT, "answer-1"),
        Message(Role.USER, "q2"),
    ]
    assert await provider.complete(conversation) == "answer-2"

    second = fake.create_calls[1]
    assistant = [m for m in second["messages"] if m["role"] == "assistant"][0]
    # passed back unmodified, like OpenRouter's docs prescribe
    assert assistant["reasoning_details"] == [{"type": "reasoning", "text": "think"}]
    assert second["extra_body"] == {"reasoning": {"enabled": True}}


async def test_anthropic_splits_system_and_joins_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    provider = AnthropicProvider(model="claude-x")
    fake = FakeAsyncAnthropic()
    provider.client = fake
    fake.script = ["block-text"]

    out = await provider.complete(
        [
            Message(Role.SYSTEM, "sys-1"),
            Message(Role.USER, "hi"),
            Message(Role.ASSISTANT, "ho"),
        ]
    )

    assert out == "block-text"
    call = fake.create_calls[0]
    assert call["system"] == "sys-1"
    assert call["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ho"},
    ]


def test_missing_sdk_adapter_raises_helpful_error(monkeypatch):
    import toolloop.providers as providers_package

    monkeypatch.setitem(providers_package._OPENAI_ADAPTERS, "OpenRouterProvider", "does_not_exist")
    with pytest.raises(ImportError, match=r"toolloop\[openai\]"):
        _ = providers_package.OpenRouterProvider
