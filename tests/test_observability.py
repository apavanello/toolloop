from __future__ import annotations

import sys

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from toolloop import Agent, tool
from toolloop.observability import otel_span, resolve_tracer
from toolloop.testing import ScriptedProvider, final_answer, tool_call


class MemoryExporter(SpanExporter):
    def __init__(self):
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None


def make_tracer():
    exporter = MemoryExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter, provider


@tool
async def echo(text: str) -> str:
    """Echo the text."""
    return text


async def test_span_tree_run_step_tool():
    tracer, exporter, otel = make_tracer()
    provider = ScriptedProvider([tool_call("echo", call_id="c1", text="hi"), final_answer("done")])
    agent = Agent(provider, tools=[echo], tracer=tracer)
    await agent.run("x")
    otel.force_flush()

    names = [span.name for span in exporter.spans]
    assert "toolloop.run" in names  # exporter order is end-order, not start-order
    assert names.count("toolloop.step") == 2
    assert "toolloop.tool" in names

    run_span = next(span for span in exporter.spans if span.name == "toolloop.run")
    tool_span = next(span for span in exporter.spans if span.name == "toolloop.tool")
    attributes = dict(tool_span.attributes)
    assert attributes["toolloop.tool.name"] == "echo"
    assert attributes["toolloop.tool.status"] == "ok"
    assert attributes["toolloop.tool.duration_s"] >= 0
    # the tool span is a child of a step span, which is a child of the run span
    step_ids = {span.context.span_id for span in exporter.spans if span.name == "toolloop.step"}
    assert tool_span.parent.span_id in step_ids
    step_span = next(
        span
        for span in exporter.spans
        if span.name == "toolloop.step" and span.context.span_id == tool_span.parent.span_id
    )
    assert step_span.parent.span_id == run_span.context.span_id


async def test_parse_error_emits_event():
    tracer, exporter, otel = make_tracer()
    provider = ScriptedProvider(["garbage, no json", final_answer("ok")])
    agent = Agent(provider, tools=[echo], tracer=tracer)
    await agent.run("x")
    otel.force_flush()

    error_steps = [span for span in exporter.spans if span.name == "toolloop.step" and span.events]
    assert error_steps
    events = error_steps[0].events
    assert events[0].name == "toolloop.parse_error"
    assert dict(events[0].attributes)["toolloop.reason"]


def test_noop_without_tracer_or_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)  # simulate absent SDK
    assert resolve_tracer() is None

    with otel_span(None, "anything") as span:
        assert span is None

    # an agent runs normally with no tracer resolved
    import asyncio

    provider = ScriptedProvider([final_answer("ok")])
    result = asyncio.run(Agent(provider, tools=[echo]).run("x"))
    assert result.output == "ok"
