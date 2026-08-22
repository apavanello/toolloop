"""The agent loop."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
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
from .observability import otel_span, resolve_tracer
from .protocol.base import FinalAnswer, ToolCallRequest, ToolProtocol
from .protocol.json_protocol import JsonToolProtocol
from .state import AgentState
from .tools.definition import ToolDefinition

logger = logging.getLogger("toolloop")


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
    usage: dict[str, Any] | None = None  # summed provider-reported usage, if any


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
        token_counter: Callable[[Sequence[Message]], int] | None = None,
        tracer: Any = None,
        max_retries: int = 0,
        retry_backoff: float = 0.5,
        provider_timeout: float | None = None,
        checkpoint: Callable[[AgentState], Any] | str | Path | None = None,
        checkpoint_every: int = 10,
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
        self.token_counter = token_counter
        self.context = (
            ContextManager(provider, max_context_tokens, token_counter=token_counter)
            if max_context_tokens
            else None
        )
        self._tracer = resolve_tracer(tracer)
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.provider_timeout = provider_timeout
        self.checkpoint = checkpoint
        self.checkpoint_every = checkpoint_every
        # live conversation of the current session (empty until the first run)
        self.conversation: list[Message] = []
        self._session_history: list[StepRecord] = []
        self._run_usage: dict[str, Any] | None = None

    async def run(
        self,
        input: str,
        *,
        max_iterations: int = 25,
        on_max: OnMax = OnMax.RAISE,
        control: ControlMode | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> RunResult:
        """Run the loop until ``final_answer``, ``max_iterations`` or a hook stops it.

        If this agent was built with ``from_state`` (or has run before), the
        new input continues the existing conversation instead of starting one.
        """
        with otel_span(self._tracer, "toolloop.run"):
            result = await self._run(
                input,
                max_iterations=max_iterations,
                on_max=on_max,
                control=control,
                output_model=output_model,
            )
            logger.info(
                "run finished: status=%s, steps=%d", result.status.value, len(result.history)
            )
            return result

    async def _run(
        self,
        input: str,
        *,
        max_iterations: int,
        on_max: OnMax,
        control: ControlMode | None,
        output_model: type[BaseModel] | None,
    ) -> RunResult:
        mode = control or self.control
        messages: list[Message] = list(self.conversation)
        history: list[StepRecord] = list(self._session_history)
        parse_failures = 0
        self._run_usage = None
        try:
            if mode is ControlMode.APPROVE and self.on_tool_call is None:
                raise ControlError(
                    "control=APPROVE requires an on_tool_call hook to approve tool "
                    "calls; pass on_tool_call=... or use ControlMode.BYPASS"
                )

            if messages:
                # resumed session: keep the conversation going
                messages.append(Message(Role.USER, input))
            else:
                instructions = self.protocol.render_instructions(list(self.registry.values()))
                system_content = (
                    f"{self.system_prompt}\n\n{instructions}"
                    if self.system_prompt
                    else instructions
                )
                messages = [
                    Message(Role.SYSTEM, system_content),
                    Message(Role.USER, input),
                ]

            for step in range(1, max_iterations + 1):
                with otel_span(
                    self._tracer, "toolloop.step", {"toolloop.step.number": step}
                ) as step_span:
                    raw = await self._generate(messages)
                    messages.append(Message(Role.ASSISTANT, raw))
                    logger.debug("step %d raw response: %s", step, raw)

                    try:
                        parsed = self.protocol.parse(raw)
                    except ParseError as exc:
                        parse_failures += 1
                        history.append(StepRecord(step=step, raw=raw, kind="parse_error"))
                        logger.warning("step %d: parse error: %s", step, exc.reason)
                        if step_span is not None:
                            step_span.set_attribute("toolloop.step.kind", "parse_error")
                            step_span.add_event(
                                "toolloop.parse_error", {"toolloop.reason": exc.reason}
                            )
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
                        if step_span is not None:
                            step_span.set_attribute("toolloop.step.kind", "final_answer")
                        logger.info("step %d: final_answer: %s", step, _preview(parsed.output))
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
                            await self._maybe_checkpoint(messages, history, force=True)
                            return self._finalize(Status.COMPLETED, value, history)
                        history.append(StepRecord(step=step, raw=raw, kind="final_answer"))
                        await self._fire_step(step, messages, raw, "final_answer", [])
                        await self._maybe_checkpoint(messages, history, force=True)
                        return self._finalize(Status.COMPLETED, parsed.output, history)

                    if step_span is not None:
                        step_span.set_attribute("toolloop.step.kind", "tool_calls")
                    call_records, observations = await self._process_calls(step, parsed.calls, mode)
                    for record in call_records:
                        logger.info(
                            "step %d: %s %s -> %s (%.2fs): %s",
                            step,
                            record.name,
                            record.args,
                            record.status,
                            record.duration,
                            _preview(record.result),
                        )
                    messages.append(Message(Role.USER, "\n".join(observations), kind="observation"))
                    history.append(
                        StepRecord(step=step, raw=raw, kind="tool_calls", calls=call_records)
                    )
                    if self.context is not None:
                        messages = await self.context.manage(messages)
                    await self._fire_step(step, messages, raw, "tool_calls", call_records)
                    await self._maybe_checkpoint(messages, history)

            return await self._handle_max(on_max, max_iterations, messages, history, output_model)
        finally:
            self.conversation = messages
            self._session_history = history

    def to_state(self) -> AgentState:
        """Snapshot the current session (conversation + audit history)."""
        return AgentState(messages=list(self.conversation), history=list(self._session_history))

    @classmethod
    def from_state(
        cls,
        state: AgentState,
        provider: Any,
        tools: Sequence[ToolDefinition] = (),
        **kwargs: Any,
    ) -> Agent:
        """Build an agent that continues the conversation stored in ``state``.

        Provider, tools and hooks are code — pass them here, not in the state.
        The next ``run()`` appends its input to the loaded conversation.
        """
        agent = cls(provider, tools, **kwargs)
        agent.conversation = list(state.messages)
        agent._session_history = list(state.history)
        return agent

    def _finalize(self, status: Status, output: Any, history: list[StepRecord]) -> RunResult:
        return RunResult(status, output, history, usage=self._run_usage)

    async def _maybe_checkpoint(
        self,
        messages: list[Message],
        history: list[StepRecord],
        force: bool = False,
    ) -> None:
        """Persist a checkpoint of the live session; failures never kill the run."""
        if self.checkpoint is None:
            return
        if not force and (len(history) % self.checkpoint_every) != 0:
            return
        state = AgentState(messages=list(messages), history=list(history))
        try:
            if callable(self.checkpoint):
                outcome = self.checkpoint(state)
                if inspect.isawaitable(outcome):
                    await outcome
            else:
                path = Path(str(self.checkpoint))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(state.to_json())
        except Exception:
            logger.exception("checkpoint failed (ignored)")
        else:
            logger.debug("checkpoint written")

    async def _generate(self, messages: list[Message]) -> str:
        """Call the provider with an optional timeout and retry/backoff.

        Transport failures (network blips, 5xx, hangs) are retried with
        exponential backoff and jitter; ``CancelledError`` always propagates —
        cancellation is never retried. Model behavior (unparseable output) is
        not retried here: the auto-repair loop owns that.
        """
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                if self.provider_timeout is not None:
                    async with asyncio.timeout(self.provider_timeout):
                        return await self._generate_once(messages)
                return await self._generate_once(messages)
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt >= attempts:
                    raise
                delay = min(self.retry_backoff * 2 ** (attempt - 1), 30.0)
                delay += random.uniform(0, delay * 0.25)
                logger.warning(
                    "provider attempt %d/%d failed; retrying in %.2fs",
                    attempt,
                    attempts,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _generate_once(self, messages: list[Message]) -> str:
        """One provider attempt; prefers streaming when both sides support it.

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
            text = "".join(chunks)
        else:
            text = await self.provider.complete(messages)
        self._collect_usage()
        return text

    def _collect_usage(self) -> None:
        """Sum the provider-reported usage of the last call, when available."""
        last_usage = getattr(self.provider, "last_usage", None)
        if not callable(last_usage):
            return
        value = last_usage()
        if isinstance(value, dict):
            self._run_usage = _merge_usage(self._run_usage, value)

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
        with otel_span(
            self._tracer,
            "toolloop.tool",
            {
                "toolloop.tool.name": call.name,
                "toolloop.tool.dangerous": tooldef.dangerous if tooldef else False,
            },
        ) as tool_span:
            ok, result = await tooldef.execute(args)
            duration = perf_counter() - started
            if tool_span is not None:
                tool_span.set_attribute("toolloop.tool.status", "ok" if ok else "error")
                tool_span.set_attribute("toolloop.tool.duration_s", round(duration, 6))
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
                    await self._maybe_checkpoint(messages, history, force=True)
                    return self._finalize(Status.COMPLETED, value, history)
            await self._maybe_checkpoint(messages, history, force=True)
            return self._finalize(Status.MAX_ITERATIONS, None, history)
        if on_max is OnMax.PARTIAL:
            await self._maybe_checkpoint(messages, history, force=True)
            return self._finalize(Status.MAX_ITERATIONS, None, history)
        logger.warning("run exhausted max_iterations (%d)", max_iterations)
        raise MaxIterationsExceeded(max_iterations, history[-1].raw if history else None)


def _merge_usage(total: dict[str, Any] | None, delta: dict[str, Any]) -> dict[str, Any]:
    merged = dict(total or {})
    for key, value in delta.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            merged[key] = merged.get(key, 0) + value
        else:
            merged[key] = value
    return merged


def _preview(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
