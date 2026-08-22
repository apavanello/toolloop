"""toolloop: agent loops for LLM providers without native tool use."""

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
from .subagent import subagent_tool
from .tools import STD_TOOLS, ToolDefinition, tool

__version__ = "0.1.0"

__all__ = [
    "Agent",
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
    "estimate_tokens",
    "subagent_tool",
    "tool",
]
