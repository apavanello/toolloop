"""Tool definition: the ``@tool`` decorator and execution semantics."""

from __future__ import annotations

import inspect
import json
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


@dataclass(frozen=True)
class ToolDefinition:
    """A tool ready to be registered on an :class:`~toolloop.Agent`."""

    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., Awaitable[Any]]
    dangerous: bool = False
    schema: dict[str, Any] | None = None  # verbatim JSON schema override (e.g. MCP)

    def json_schema(self) -> dict[str, Any]:
        return self.schema if self.schema is not None else self.args_model.model_json_schema()

    async def execute(self, args: dict[str, Any]) -> tuple[bool, str]:
        """Validate ``args``, run the tool, return ``(ok, observation)``.

        Invalid arguments and raised exceptions become error observations the
        model can repair from — they never abort the agent loop.
        """
        try:
            validated = self.args_model.model_validate(args)
        except ValidationError as exc:
            return False, _format_validation_error(exc)
        kwargs = {name: getattr(validated, name) for name in type(validated).model_fields}
        extra = getattr(validated, "__pydantic_extra__", None)
        if extra:
            kwargs.update(extra)  # pass-through tools (extra="allow") keep their args
        try:
            result = await self.func(**kwargs)
        except Exception as exc:  # tool errors are observations, not crashes
            return False, f"{type(exc).__name__}: {exc}"
        return True, _render_result(result)


def _render_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str, ensure_ascii=False)


def _format_validation_error(exc: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(loc) for loc in error['loc']) or '(root)'}: {error['msg']}"
        for error in exc.errors()
    )
    return f"invalid arguments ({problems})"


def tool(
    fn: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    dangerous: bool = False,
) -> Callable[[F], ToolDefinition] | ToolDefinition:
    """Turn an async function into a :class:`ToolDefinition`.

    Usable bare (``@tool``), empty (``@tool()``) or configured
    (``@tool(dangerous=True)``). The argument schema is derived from type
    hints; the description comes from the docstring.
    """

    def wrap(fn: F) -> ToolDefinition:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"tool {fn.__name__!r} must be an async function (async def)")
        tool_name = name or fn.__name__
        return ToolDefinition(
            name=tool_name,
            description=description or inspect.getdoc(fn) or "",
            args_model=_build_args_model(fn, tool_name),
            func=fn,
            dangerous=dangerous,
        )

    return wrap(fn) if fn is not None else wrap


def _build_args_model(fn: Callable[..., Awaitable[Any]], tool_name: str) -> type[BaseModel]:
    hints = typing.get_type_hints(fn)
    fields: dict[str, Any] = {}
    for param in inspect.signature(fn).parameters.values():
        if param.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            raise TypeError(
                f"tool {tool_name!r}: parameter {param.name!r} must be a plain "
                "keyword-able parameter (no *args/**kwargs)"
            )
        annotation = hints.get(param.name, str)
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param.name] = (annotation, default)
    return create_model(
        f"{tool_name}__args",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
