"""Context-window management: truncation of old observations + compaction."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ._types import Message, Role

_SUMMARY_SYSTEM = (
    "Summarize the following agent conversation compactly. Preserve: the "
    "original task, key findings, decisions made, essential tool results, and "
    "the current state. Reply with the summary only."
)


def estimate_tokens(messages: Sequence[Message]) -> int:
    """Rough token estimate (~4 chars per token, plus per-message overhead)."""
    return sum(len(message.content) // 4 + 8 for message in messages)


class ContextManager:
    """Keeps the conversation within ``max_tokens`` using a heuristic estimate.

    Two stages, cheapest first: truncate the oldest tool observations to a
    short preview, then compact by asking the provider itself to summarize the
    middle of the conversation (the system prompt and the most recent messages
    are always preserved).
    """

    keep_recent_observations = 2
    observation_head_chars = 200

    def __init__(
        self,
        provider,
        max_tokens: int,
        token_counter: Callable[[Sequence[Message]], int] | None = estimate_tokens,
    ):
        self.provider = provider
        self.max_tokens = max_tokens
        self.token_counter = token_counter or estimate_tokens

    async def manage(self, messages: list[Message]) -> list[Message]:
        if self.token_counter(messages) <= self.max_tokens:
            return messages
        messages = self._truncate_observations(messages)
        if self.token_counter(messages) <= self.max_tokens:
            return messages
        return await self._compact(messages)

    def _truncate_observations(self, messages: list[Message]) -> list[Message]:
        out = list(messages)
        indexes = [i for i, message in enumerate(out) if message.kind == "observation"]
        preserved = set(indexes[-self.keep_recent_observations :])
        for index in indexes:  # oldest first, stop as soon as we fit
            if index in preserved or self.token_counter(out) <= self.max_tokens:
                continue
            head = out[index].content[: self.observation_head_chars]
            replacement = f"{head}\n...[older observation truncated]"
            out[index] = Message(out[index].role, replacement, out[index].kind)
        return out

    async def _compact(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= 3:  # nothing meaningful to summarize
            return messages
        head = messages[0]  # system prompt stays
        tail = messages[-2:]
        middle = messages[1 : len(messages) - len(tail)]
        if not middle:
            return messages
        transcript = "\n".join(f"{m.role.value}: {m.content}" for m in middle)
        summary = await self.provider.complete(
            [
                Message(Role.SYSTEM, _SUMMARY_SYSTEM),
                Message(Role.USER, transcript),
            ]
        )
        budget_chars = max(
            0,
            (self.max_tokens - self.token_counter([head, *tail])) * 4,
        )
        if len(summary) > budget_chars:
            summary = summary[:budget_chars] + "\n...[summary truncated]"
        return [head, Message(Role.USER, f"[conversation summary]\n{summary}"), *tail]
