# Providers

## The contract

::: toolloop.Provider

## OpenAI-compatible endpoints

::: toolloop.providers.openai_compat.OpenAICompatProvider

## OpenRouter

::: toolloop.providers.openrouter.OpenRouterProvider

## Anthropic

::: toolloop.providers.anthropic.AnthropicProvider

!!! note
    Adapters are installed via extras: `pip install "toolloop[openai]"` /
    `pip install "toolloop[anthropic]"`. Importing one without its SDK
    raises an `ImportError` telling you which extra to install.
