"""Pluggable tool-call protocols: how tools are advertised and responses parsed."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..tools.definition import ToolDefinition


@dataclass(frozen=True)
class ToolCallRequest:
    """A single tool call requested by the model."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolCalls:
    """A parsed ``tool_call`` envelope."""

    calls: list[ToolCallRequest]


@dataclass(frozen=True)
class FinalAnswer:
    """A parsed ``final_answer`` envelope; ``output`` is usually a string."""

    output: Any


class ToolProtocol(ABC):
    """Renders tool instructions into the system prompt and parses responses.

    A protocol is the pair (prompt renderer, response parser). The default is
    :class:`~toolloop.protocol.json_protocol.JsonToolProtocol`; write your own
    to speak ReAct, XML tags, or anything else your provider's models prefer.
    """

    @abstractmethod
    def render_instructions(self, tools: Sequence[ToolDefinition]) -> str:
        """Return the tool-use instructions to append to the system prompt."""

    @abstractmethod
    def parse(self, text: str) -> ToolCalls | FinalAnswer:
        """Parse a raw model response; raise :class:`ParseError` when invalid."""
