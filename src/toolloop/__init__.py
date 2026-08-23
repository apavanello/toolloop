"""toolloop: agent loops for LLM providers without native tool use."""

from . import providers  # noqa: F401  (lazy adapters; safe without SDKs)
from ._types import (
    ControlError,
    MaxIterationsExceeded,
    Message,
    ParseError,
    ParseLoopError,
    Role,
    Status,
    StepRecord,
    ToolCallRecord,
)
from .agent import Agent, OnMax, RunResult
from .approval import console_approver
from .context import ContextManager, estimate_tokens
from .hooks import ControlMode, Decision, StepContext, ToolCallContext, ToolResultContext
from .protocol import (
    FinalAnswer,
    JsonToolProtocol,
    ToolCallRequest,
    ToolCalls,
    ToolProtocol,
)
from .provider import Provider
from .resilience import rate_limited
from .state import AgentState
from .subagent import subagent_tool
from .sync import run_sync
from .testing import ScriptedProvider, final_answer, tool_call
from .tools import STD_TOOLS, ToolDefinition, tool

__version__ = "1.1.0"

__all__ = [
    "Agent",
    "AgentState",
    "ContextManager",
    "ControlError",
    "ControlMode",
    "Decision",
    "FinalAnswer",
    "MaxIterationsExceeded",
    "Message",
    "OnMax",
    "ParseError",
    "ParseLoopError",
    "Provider",
    "Role",
    "RunResult",
    "Status",
    "StepContext",
    "StepRecord",
    "STD_TOOLS",
    "ToolCallContext",
    "ToolCallRecord",
    "ToolCallRequest",
    "ToolCalls",
    "ToolDefinition",
    "ToolProtocol",
    "ToolResultContext",
    "JsonToolProtocol",
    "ScriptedProvider",
    "console_approver",
    "estimate_tokens",
    "final_answer",
    "rate_limited",
    "run_sync",
    "subagent_tool",
    "tool",
    "tool_call",
]
