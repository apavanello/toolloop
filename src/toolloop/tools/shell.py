"""``bash``: shell execution tool."""

from __future__ import annotations

import asyncio

from .definition import tool

MAX_OUTPUT_CHARS = 8_000


@tool(dangerous=True)
async def bash(command: str, timeout: float = 60.0, cwd: str | None = None) -> str:
    """Run a shell command; returns its exit code and combined stdout/stderr."""
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"command timed out after {timeout:.0f}s and was killed") from None
    text = out.decode(errors="replace")
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n...[output truncated, {len(text)} chars total]"
    return f"exit code: {proc.returncode}\n{text}"
