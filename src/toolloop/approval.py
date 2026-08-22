"""A ready-made human-in-the-loop approver for ``ControlMode.APPROVE``."""

from __future__ import annotations

from collections.abc import Callable

from .hooks import Decision, ToolCallContext


def console_approver(prompt: Callable[[str], str] = input):
    """Build an ``on_tool_call`` hook that asks a human about dangerous tools.

    Safe tools are allowed silently; tools marked ``dangerous=True`` get a
    terminal prompt. Pass your own (sync) ``prompt`` callable in tests to
    avoid touching ``input()``.
    """

    async def approver(ctx: ToolCallContext) -> Decision:
        if not ctx.dangerous:
            return Decision.allow()
        answer = prompt(f"allow {ctx.name}({ctx.args})? [y/N] ")
        if answer.strip().lower() == "y":
            return Decision.allow()
        return Decision.deny("denied by human")

    return approver
