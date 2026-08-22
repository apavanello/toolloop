"""Async hooks and control modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ._types import Message, ToolCallRecord


class ControlMode(StrEnum):
    """Who is allowed to run tool calls.

    - ``APPROVE``: default-deny. Every tool call must be explicitly allowed by
      an ``on_tool_call`` hook (human-in-the-loop).
    - ``BYPASS``: default-allow. Fully autonomous; hooks can still deny or
      modify calls.
    """

    APPROVE = "approve"
    BYPASS = "bypass"


@dataclass
class Decision:
    """Verdict of an ``on_tool_call`` hook."""

    allowed: bool
    args: dict[str, Any] | None = None  # replacement args, when allowed
    reason: str = ""

    @classmethod
    def allow(cls, args: dict[str, Any] | None = None) -> Decision:
        return cls(allowed=True, args=args)

    @classmethod
    def deny(cls, reason: str = "denied") -> Decision:
        return cls(allowed=False, reason=reason)


@dataclass
class StepContext:
    """Context passed to ``on_step`` after each provider call is processed."""

    step: int
    messages: list[Message]  # live conversation; read-only by convention
    raw: str | None  # the provider response for this step, if any
    kind: str  # "tool_calls" | "final_answer" | "parse_error"
    calls: list[ToolCallRecord] = field(default_factory=list)


@dataclass
class ToolCallContext:
    """Context passed to ``on_tool_call`` before execution."""

    step: int
    call_id: str
    name: str
    args: dict[str, Any]
    dangerous: bool


@dataclass
class ToolResultContext:
    """Context passed to ``on_tool_result`` after execution (or denial)."""

    step: int
    call_id: str
    name: str
    args: dict[str, Any]
    status: str  # "ok" | "error" | "denied"
    result: str
    duration: float
