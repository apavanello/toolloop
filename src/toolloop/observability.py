"""OpenTelemetry auto-instrumentation (optional, zero-cost when the SDK is absent).

The agent loop emits a span tree automatically::

    toolloop.run
      toolloop.step   (attributes: step number, kind; parse errors as events)
        toolloop.tool (attributes: name, dangerous, status, duration)

Install the SDK with ``pip install "toolloop[otel]"``. Without it,
``resolve_tracer`` returns None and every span becomes a no-op — the core
never imports opentelemetry directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def resolve_tracer(tracer: Any = None) -> Any:
    """Return ``tracer`` if given; else the global OTel tracer; else None."""
    if tracer is not None:
        return tracer
    try:
        from opentelemetry.trace import get_tracer
    except ImportError:  # SDK not installed: instrumentation becomes a no-op
        return None
    return get_tracer("toolloop")


@contextmanager
def otel_span(tracer: Any, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Yield an active span, or None when there is no tracer."""
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as current:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    current.set_attribute(key, value)
        yield current
