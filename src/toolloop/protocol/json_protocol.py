"""Default protocol: a JSON envelope discriminated by ``type``."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from typing import Any

from .._types import ParseError
from ..tools.definition import ToolDefinition
from .base import FinalAnswer, ToolCallRequest, ToolCalls, ToolProtocol

_FENCE_RE = re.compile(r"```[a-zA-Z]*\s*([\s\S]*?)```")


class JsonToolProtocol(ToolProtocol):
    """Advertises tools with JSON schemas and parses a JSON envelope.

    Envelopes::

        {"type": "tool_call", "calls": [{"id": "c1", "name": "...", "args": {...}}]}
        {"type": "final_answer", "output": ...}

    Parsing is tolerant: fenced code blocks (the last valid one wins) or a
    bare JSON object, with or without surrounding prose. Every failure raises
    :class:`ParseError` with an instructive message so the agent loop can feed
    it back to the model (auto-repair).
    """

    def render_instructions(self, tools: Sequence[ToolDefinition]) -> str:
        lines = [
            "# Tool use",
            "",
            "You can call tools. To call tools, respond with ONLY a JSON object of",
            'type "tool_call" (a fenced ```json block is preferred):',
            "",
            '{"type": "tool_call", "calls": [{"id": "call-1", "name": "<tool>", "args": {...}}]}',
            "",
            "Calls run sequentially; you will receive their results as observations",
            "in the next message. `args` must match the tool's argument schema.",
            "",
            "When you are satisfied and no longer need tools, respond with ONLY:",
            "",
            '{"type": "final_answer", "output": <your answer>}',
            "",
            "`output` is a string unless another format was requested. Never emit",
            "prose outside the JSON envelope.",
            "",
            "## Available tools",
            "",
        ]
        for tool_ in tools:
            lines.append(f"### {tool_.name}")
            if tool_.description:
                lines.append(tool_.description)
            lines.append("argument schema: " + json.dumps(tool_.json_schema(), ensure_ascii=False))
            lines.append("")
        return "\n".join(lines).rstrip()

    def parse(self, text: str) -> ToolCalls | FinalAnswer:
        errors: list[str] = []
        for candidate in self._candidates(text):
            try:
                return self._parse_envelope(candidate)
            except ParseError as exc:
                errors.append(exc.reason)
        first = errors[0] if errors else "no JSON found"
        raise ParseError(
            f"could not find a valid JSON envelope ({first}); expected "
            '{"type": "tool_call", "calls": [...]} or '
            '{"type": "final_answer", "output": ...}',
            text,
        )

    def _candidates(self, text: str) -> list[str]:
        fenced = [match.group(1).strip() for match in _FENCE_RE.finditer(text)]
        return list(reversed(fenced)) + [text.strip()]

    def _parse_envelope(self, candidate: str) -> ToolCalls | FinalAnswer:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ParseError(f"invalid JSON ({exc.msg})", candidate) from None
        if not isinstance(obj, dict):
            raise ParseError(f"envelope must be a JSON object, got {type(obj).__name__}", candidate)
        kind = obj.get("type")
        if kind == "final_answer":
            return FinalAnswer(output=obj.get("output", ""))
        if kind == "tool_call":
            calls_raw = obj.get("calls")
            if not isinstance(calls_raw, list) or not calls_raw:
                raise ParseError('"tool_call" requires a non-empty "calls" list', candidate)
            calls = [self._parse_call(index, call) for index, call in enumerate(calls_raw)]
            return ToolCalls(calls=calls)
        raise ParseError(f'"type" must be "tool_call" or "final_answer", got {kind!r}', candidate)

    def _parse_call(self, index: int, raw: Any) -> ToolCallRequest:
        if not isinstance(raw, dict):
            raise ParseError(f"call #{index} must be a JSON object", str(raw))
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ParseError(f"call #{index} requires a non-empty string 'name'", str(raw))
        args = raw.get("args", {})
        if not isinstance(args, dict):
            raise ParseError(f"call #{index} 'args' must be a JSON object", str(raw))
        call_id = str(raw.get("id") or f"call-{index + 1}-{uuid.uuid4().hex[:6]}")
        return ToolCallRequest(id=call_id, name=name, args=args)
