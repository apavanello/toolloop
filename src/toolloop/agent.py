"""The agent loop."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

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
from .context import ContextManager
from .hooks import (
    ControlMode,
    Decision,
    StepContext,
    ToolCallContext,
    ToolResultContext,
)
from .protocol.base import FinalAnswer, ToolProtocol
from .protocol.json_protocol import JsonToolProtocol
from .tools.definition import ToolDefinition


class OnMax(StrEnum):
    """What to do when ``max_iterations`` is exhausted."""

    RAISE = "raise"  # raise MaxIterationsExceeded
    WRAP_UP = "wrap_up"  # one forced extra turn: "answer now"
    PARTIAL = "partial"  # return RunResult(status=MAX_ITERATIONS, output=None)


@dataclass
class RunResult:
    """Final outcome of ``Agent.run`` with a full audit trail."""

    status: Status
    output: Any = None
    history: list[StepRecord] = field(default_factory=list)


class Agent:
    """An autonomous loop: input -> tool calls -> final answer.

    The provider never sees tool-use APIs. The protocol renders tool
    instructions into the system prompt and parses tool calls out of the
    model's plain-text responses; results are fed back as observations until
    the model emits a ``final_answer`` envelope.
    """

    def __init__(
        self,
        provider,
        tools: Sequence[ToolDefinition] = (),
        *,
        protocol: ToolProtocol | None = None,
        system_prompt: str | None = None,
        control: ControlMode = ControlMode.BYPASS,
        on_step: Callable[[StepContext], Any] | None = None,
        on_tool_call: Callable[[ToolCallContext], Any] | None = None,
        on_tool_result: Callable[[ToolResultContext], Any] | None = None,
        max_context_tokens: int | None = None,
        max_parse_failures: int = 3,
        max_tool_result_chars: int = 10_000,
    ) -> None:
        self.provider = provider
        self.protocol = protocol or JsonToolProtocol()
        self.system_prompt = system_prompt
        self.control = control
        self.on_step = on_step
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result
        self.max_parse_failures = max_parse_failures
        self.max_tool_result_chars = max_tool_result_chars
        self.registry: dict[str, ToolDefinition] = {t.name: t for t in tools}
        if len(self.registry) != len(tools):
            raise ValueError("duplicate tool names in Agent(tools=...)")
        self.context = ContextManager(provider, max_context_tokens) if max_context_tokens else None

    async def run(
        self,
        input: str,
        *,
        max_iterations: int = 25,
        on_max: OnMax = OnMax.RAISE,
        control: ControlMode | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> RunResult:
        """Run the loop until ``final_answer``, ``max_iterations`` or a hook stops it."""
        mode = control or self.control
        if mode is ControlMode.APPROVE and self.on_tool_call is None:
            raise ControlError(
                "control=APPROVE requires an on_tool_call hook to approve tool "
                "calls; pass on_tool_call=... or use ControlMode.BYPASS"
            )

        instructions = self.protocol.render_instructions(list(self.registry.values()))
        system_content = (
            f"{self.system_prompt}\n\n{instructions}" if self.system_prompt else instructions
        )
        messages: list[Message] = [
            Message(Role.SYSTEM, system_content),
            Message(Role.USER, input),
        ]
        history: list[StepRecord] = []
        parse_failures = 0

        for step in range(1, max_iterations + 1):
            raw = await self.provider.complete(messages)
            messages.append(Message(Role.ASSISTANT, raw))

            try:
                parsed = self.protocol.parse(raw)
            except ParseError as exc:
                parse_failures += 1
                history.append(StepRecord(step=step, raw=raw, kind="parse_error"))
                if parse_failures >= self.max_parse_failures:
                    await self._fire_step(step, messages, raw, "parse_error", [])
                    raise ParseLoopError(
                        f"{parse_failures} consecutive unparseable responses; "
                        f"last error: {exc.reason}"
                    ) from exc
                messages.append(
                    Message(
                        Role.USER,
                        f"Your last response could not be parsed: {exc.reason}\n"
                        "Respond again with a single JSON envelope "
                        "(tool_call or final_answer) and no other text.",
                        kind="observation",
                    )
                )
                await self._fire_step(step, messages, raw, "parse_error", [])
                continue
            parse_failures = 0

            if isinstance(parsed, FinalAnswer):
                if output_model is not None:
                    value, error = _validate_output(parsed.output, output_model)
                    if error is not None:
                        history.append(StepRecord(step=step, raw=raw, kind="parse_error"))
                        messages.append(
                            Message(
                                Role.USER,
                                f"Your final_answer output is invalid: {error}\n"
                                "Respond again with a corrected final_answer envelope.",
                                kind="observation",
                            )
                        )
                        await self._fire_step(step, messages, raw, "parse_error", [])
                        continue
                    history.append(StepRecord(step=step, raw=raw, kind="final_answer"))
                    await self._fire_step(step, messages, raw, "final_answer", [])
                    return RunResult(Status.COMPLETED, value, history)
                history.append(StepRecord(step=step, raw=raw, kind="final_answer"))
                await self._fire_step(step, messages, raw, "final_answer", [])
                return RunResult(Status.COMPLETED, parsed.output, history)

            call_records: list[ToolCallRecord] = []
            observations: list[str] = []
            for call in parsed.calls:  # sequential in v1
                record, observation = await self._run_call(step, call, mode)
                call_records.append(record)
                observations.append(f"[{record.call_id}] {observation}")
            messages.append(Message(Role.USER, "\n".join(observations), kind="observation"))
            history.append(StepRecord(step=step, raw=raw, kind="tool_calls", calls=call_records))
            if self.context is not None:
                messages = await self.context.manage(messages)
            await self._fire_step(step, messages, raw, "tool_calls", call_records)

        return await self._handle_max(on_max, max_iterations, messages, history, output_model)

    async def _run_call(self, step: int, call, mode: ControlMode) -> tuple[ToolCallRecord, str]:
        tooldef = self.registry.get(call.name)
        args = dict(call.args)
        dangerous = tooldef.dangerous if tooldef else False

        decision: Decision | None = None
        if self.on_tool_call is not None:
            decision = await self.on_tool_call(
                ToolCallContext(
                    step=step,
                    call_id=call.id,
                    name=call.name,
                    args=args,
                    dangerous=dangerous,
                )
            )
        allowed = mode is ControlMode.BYPASS
        if decision is not None:
            allowed = decision.allowed
        if not allowed:
            reason = (decision.reason if decision else "") or "denied by policy"
            return await self._finish_call(
                step,
                ToolCallRecord(
                    call_id=call.id, name=call.name, args=args, status="denied", result=reason
                ),
                f"DENIED: {reason}",
            )
        if decision is not None and decision.args is not None:
            args = dict(decision.args)

        if tooldef is None:
            message = (
                f"unknown tool {call.name!r}; available tools: {', '.join(sorted(self.registry))}"
            )
            return await self._finish_call(
                step,
                ToolCallRecord(
                    call_id=call.id,
                    name=call.name,
                    args=args,
                    status="error",
                    result=message,
                ),
                f"ERROR: {message}",
            )

        started = perf_counter()
        ok, result = await tooldef.execute(args)
        duration = perf_counter() - started
        if len(result) > self.max_tool_result_chars:
            result = result[: self.max_tool_result_chars] + "\n...[result truncated]"
        return await self._finish_call(
            step,
            ToolCallRecord(
                call_id=call.id,
                name=call.name,
                args=args,
                status="ok" if ok else "error",
                result=result,
                duration=duration,
            ),
            result if ok else f"ERROR: {result}",
        )

    async def _finish_call(
        self, step: int, record: ToolCallRecord, observation: str
    ) -> tuple[ToolCallRecord, str]:
        if self.on_tool_result is not None:
            await self.on_tool_result(
                ToolResultContext(
                    step=step,
                    call_id=record.call_id,
                    name=record.name,
                    args=record.args,
                    status=record.status,
                    result=record.result,
                    duration=record.duration,
                )
            )
        return record, observation

    async def _fire_step(
        self,
        step: int,
        messages: list[Message],
        raw: str,
        kind: str,
        calls: list[ToolCallRecord],
    ) -> None:
        if self.on_step is not None:
            await self.on_step(
                StepContext(step=step, messages=messages, raw=raw, kind=kind, calls=list(calls))
            )

    async def _handle_max(
        self,
        on_max: OnMax,
        max_iterations: int,
        messages: list[Message],
        history: list[StepRecord],
        output_model: type[BaseModel] | None,
    ) -> RunResult:
        if on_max is OnMax.WRAP_UP:
            messages.append(
                Message(
                    Role.USER,
                    "You have reached the maximum number of iterations. Respond NOW "
                    'with your final_answer envelope ({"type": "final_answer", '
                    '"output": ...}).',
                    kind="observation",
                )
            )
            raw = await self.provider.complete(messages)
            messages.append(Message(Role.ASSISTANT, raw))
            try:
                parsed = self.protocol.parse(raw)
            except ParseError:
                parsed = None
            if isinstance(parsed, FinalAnswer):
                value: Any = None
                if output_model is None:
                    value = parsed.output
                else:
                    value, error = _validate_output(parsed.output, output_model)
                    if error is not None:
                        value = None
                if value is not None or output_model is None:
                    history.append(
                        StepRecord(step=max_iterations + 1, raw=raw, kind="final_answer")
                    )
                    return RunResult(Status.COMPLETED, value, history)
            return RunResult(Status.MAX_ITERATIONS, None, history)
        if on_max is OnMax.PARTIAL:
            return RunResult(Status.MAX_ITERATIONS, None, history)
        raise MaxIterationsExceeded(max_iterations, history[-1].raw if history else None)


def _validate_output(output: Any, model: type[BaseModel]) -> tuple[BaseModel | None, str | None]:
    value = output
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return (
                None,
                "expected a JSON object matching the required schema, got a non-JSON string",
            )
    if not isinstance(value, dict):
        return (
            None,
            f"expected a JSON object matching the required schema, got {type(value).__name__}",
        )
    try:
        return model.model_validate(value), None
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        return None, f"schema validation failed ({problems})"
