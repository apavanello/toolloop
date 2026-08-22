"""Ready-made provider adapters (optional extras).

Install the SDK for the adapter you need::

    pip install "toolloop[openai]"      # OpenAICompatProvider + OpenRouterProvider
    pip install "toolloop[anthropic]"   # AnthropicProvider

Adapters are imported lazily: accessing one without its SDK installed raises
an ``ImportError`` telling you which extra to install.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - static analysis only
    from .anthropic import AnthropicProvider
    from .openai_compat import OpenAICompatProvider
    from .openrouter import OpenRouterProvider

__all__ = ["OpenAICompatProvider", "OpenRouterProvider", "AnthropicProvider"]

_OPENAI_ADAPTERS = {"OpenAICompatProvider": "openai_compat", "OpenRouterProvider": "openrouter"}
_ANTHROPIC_ADAPTERS = {"AnthropicProvider": "anthropic"}


def _lookup(names: dict[str, str], extra: str, name: str) -> Any:
    try:
        module = __import__(f"toolloop.providers.{names[name]}", fromlist=[name])
    except ImportError as exc:
        raise ImportError(
            f'{name} requires its SDK; install it with: pip install "toolloop[{extra}]"'
        ) from exc
    return getattr(module, name)


def __getattr__(name: str) -> Any:
    if name in _OPENAI_ADAPTERS:
        return _lookup(_OPENAI_ADAPTERS, "openai", name)
    if name in _ANTHROPIC_ADAPTERS:
        return _lookup(_ANTHROPIC_ADAPTERS, "anthropic", name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
