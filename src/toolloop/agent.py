"""The agent loop."""

from __future__ import annotations

import asyncio
import inspect
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
from .protocol.base import FinalAnswer, ToolCallRequest, ToolProtocol
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
        on_delta: Callable[[str], Any] | None = None,
        max_parallel_calls: int | None = None,
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
        self.on_delta = on_delta
        if max_parallel_calls is not None and max_parallel_calls < 1:
            raise ValueError("max_parallel_calls must be >= 1 (or None for sequential)")
        self.max_parallel_calls = max_parallel_calls
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
            raw = await self._generate(messages)
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

            call_records, observations = await self._process_calls(step, parsed.calls, mode)
            messages.append(Message(Role.USER, "\n".join(observations), kind="observation"))
            history.append(StepRecord(step=step, raw=raw, kind="tool_calls", calls=call_records))
            if self.context is not None:
                messages = await self.context.manage(messages)
            await self._fire_step(step, messages, raw, "tool_calls", call_records)

        return await self._handle_max(on_max, max_iterations, messages, history, output_model)

    async def _generate(self, messages: list[Message]) -> str:
        """Call the provider; prefer streaming when both sides support it.

        Streaming is UX-only: deltas are forwarded to ``on_delta`` and the
        accumulated text is used exactly like a ``complete()`` response.
        """
        stream = getattr(self.provider, "stream", None)
        if stream is not None and self.on_delta is not None:
            chunks: list[str] = []
            async for delta in stream(messages):
                chunks.append(delta)
                outcome = self.on_delta(delta)
                if inspect.isawaitable(outcome):
                    await outcome
            return "".join(chunks)
        return await self.provider.complete(messages)

    async def _process_calls(
        self, step: int, calls: list[ToolCallRequest], mode: ControlMode
    ) -> tuple[list[ToolCallRecord], list[str]]:
        if self.max_parallel_calls is None or len(calls) <= 1:
            return await self._run_calls_sequential(step, calls, mode)
        return await self._run_calls_parallel(step, calls, mode)

    async def _run_calls_sequential(
        self, step: int, calls: list[ToolCallRequest], mode: ControlMode
    ) -> tuple[list[ToolCallRecord], list[str]]:
        records: list[ToolCallRecord] = []
        observations: list[str] = []
        for call in calls:
            allowed, args, reason = await self._gate(step, call, mode)
            if not allowed:
                record = self._denied_record(call, args, reason)
            else:
                record = await self._execute(call, args)
            await self._fire_tool_result(step, record)
            records.append(record)
            observations.append(f"[{record.call_id}] {self._observation(record)}")
        return records, observations

    async def _run_calls_parallel(
        self, step: int, calls: list[ToolCallRequest], mode: ControlMode
    ) -> tuple[list[ToolCallRecord], list[str]]:
        # Phase 1 — gating is always sequential, so approvals and vetoes are
        # deterministic (a human is never asked two questions at once).
        planned: list[tuple[ToolCallRequest, dict, bool, str]] = []
        for call in calls:
            allowed, args, reason = await self._gate(step, call, mode)
            planned.append((call, args, allowed, reason))
        # Phase 2 — approved calls execute concurrently, capped by a semaphore;
        # results are reassembled in the original call order.
        semaphore = asyncio.Semaphore(self.max_parallel_calls)
        records: list[ToolCallRecord | None] = [None] * len(calls)

        async def run_one(index: int) -> None:
            call, args, allowed, reason = planned[index]
            if not allowed:
                record = self._denied_record(call, args, reason)
            else:
                async with semaphore:
                    record = await self._execute(call, args)
            await self._fire_tool_result(step, record)  # fires as each finishes
            records[index] = record

        await asyncio.gather(*(run_one(index) for index in range(len(calls))))
        final_records = [record for record in records if record is not None]
        observations = [f"[{r.call_id}] {self._observation(r)}" for r in final_records]
        return final_records, observations

    def _denied_record(self, call: ToolCallRequest, args: dict, reason: str) -> ToolCallRecord:
        return ToolCallRecord(
            call_id=call.id, name=call.name, args=args, status="denied", result=reason
        )

    async def _gate(
        self, step: int, call: ToolCallRequest, mode: ControlMode
    ) -> tuple[bool, dict, str]:
        """Apply the on_tool_call hook and control mode; (allowed, args, reason)."""
        tooldef = self.registry.get(call.name)
        args = dict(call.args)
        decision: Decision | None = None
        if self.on_tool_call is not None:
            decision = await self.on_tool_call(
                ToolCallContext(
                    step=step,
                    call_id=call.id,
                    name=call.name,
                    args=args,
                    dangerous=tooldef.dangerous if tooldef else False,
                )
            )
        allowed = mode is ControlMode.BYPASS
        if decision is not None:
            allowed = decision.allowed
        if not allowed:
            reason = (decision.reason if decision else "") or "denied by policy"
            return False, args, reason
        if decision is not None and decision.args is not None:
            args = dict(decision.args)
        return True, args, ""

    async def _execute(self, call: ToolCallRequest, args: dict) -> ToolCallRecord:
        tooldef = self.registry.get(call.name)
        if tooldef is None:
            message = (
                f"unknown tool {call.name!r}; available tools: {', '.join(sorted(self.registry))}"
            )
            return ToolCallRecord(
                call_id=call.id, name=call.name, args=args, status="error", result=message
            )
        started = perf_counter()
        ok, result = await tooldef.execute(args)
        duration = perf_counter() - started
        if len(result) > self.max_tool_result_chars:
            result = result[: self.max_tool_result_chars] + "\n...[result truncated]"
        return ToolCallRecord(
            call_id=call.id,
            name=call.name,
            args=args,
            status="ok" if ok else "error",
            result=result,
            duration=duration,
        )

    async def _fire_tool_result(self, step: int, record: ToolCallRecord) -> None:
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

    @staticmethod
    def _observation(record: ToolCallRecord) -> str:
        if record.status == "denied":
            return f"DENIED: {record.result}"
        if record.status == "error":
            return f"ERROR: {record.result}"
        return record.result

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
            raw = await self._generate(messages)
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
