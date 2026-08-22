"""Core types shared across toolloop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Conversation role. Providers only ever see system/user/assistant."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    """A plain-text chat message exchanged with the provider.

    ``kind`` is framework metadata (e.g. ``"observation"`` for tool results)
    used by context management; providers must ignore it and render only
    ``role``/``content``.
    """

    role: Role
    content: str
    kind: str | None = None


class ToolloopError(Exception):
    """Base class for all toolloop errors."""


class ParseError(ToolloopError):
    """A model response could not be parsed into a valid envelope."""

    def __init__(self, reason: str, raw: str):
        super().__init__(reason)
        self.reason = reason
        self.raw = raw


class ParseLoopError(ToolloopError):
    """Too many consecutive unparseable responses: auto-repair gave up."""


class ControlError(ToolloopError):
    """Invalid control-mode configuration (e.g. APPROVE without an approver)."""


class MaxIterationsExceeded(ToolloopError):
    """``run()`` exhausted ``max_iterations`` with ``OnMax.RAISE``."""

    def __init__(self, steps: int, last_raw: str | None):
        super().__init__(f"agent exceeded max iterations ({steps})")
        self.steps = steps
        self.last_raw = last_raw


class Status(StrEnum):
    """Outcome of an agent run."""

    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class ToolCallRecord:
    """Audit record for one tool call (or its denial)."""

    call_id: str
    name: str
    args: dict[str, Any]
    status: str  # "ok" | "error" | "denied"
    result: str
    duration: float = 0.0


@dataclass
class StepRecord:
    """Audit record for one agent step (one provider call)."""

    step: int
    raw: str
    kind: str  # "tool_calls" | "final_answer" | "parse_error"
    calls: list[ToolCallRecord] = field(default_factory=list)
