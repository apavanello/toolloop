"""Filesystem tools with compact results by design.

Results are deliberately terse: a write tool confirms how much it wrote
instead of echoing the content, trusting the sub-execution (the framework
philosophy for keeping context small).
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from .definition import tool

MAX_READ_CHARS = 20_000
MAX_LIST = 500
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
    }
)


@tool
async def read_file(path: str, offset: int = 0, limit: int | None = None) -> str:
    """Read a text file. ``offset`` is the 0-based starting line; ``limit`` caps lines read."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    end = offset + limit if limit is not None else None
    selected = lines[offset:end]
    body = "\n".join(selected)
    notes = []
    if offset or limit is not None:
        notes.append(f"lines {offset}..{offset + max(len(selected), 1) - 1} of {len(lines)}")
    if len(body) > MAX_READ_CHARS:
        body = body[:MAX_READ_CHARS] + "\n...[file truncated]"
        notes.append("truncated")
    return body + (f"\n[{'; '.join(notes)}]" if notes else "")


@tool
async def write_file(path: str, content: str) -> str:
    """Write ``content`` to a file, creating parent directories. Confirms size only."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"


@tool
async def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replace ``old_string`` with ``new_string``; match must be unique unless ``replace_all``."""
    if not old_string:
        raise ValueError("old_string must not be empty")
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old_string)
    if count == 0:
        raise ValueError(f"old_string not found in {path}")
    if count > 1 and not replace_all:
        raise ValueError(
            f"old_string matches {count} times in {path}; make it unique or pass replace_all=true"
        )
    replacements = count if replace_all else 1
    file_path.write_text(
        text.replace(old_string, new_string)
        if replace_all
        else text.replace(old_string, new_string, 1),
        encoding="utf-8",
    )
    return f"replaced {replacements} occurrence(s) in {path}"


@tool
async def list_files(path: str = ".", pattern: str | None = None) -> str:
    """List files recursively, skipping VCS/dependency dirs; ``pattern`` is an fnmatch glob."""
    entries: list[str] = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            if pattern is not None and not fnmatch.fnmatch(filename, pattern):
                continue
            entries.append(os.path.relpath(os.path.join(dirpath, filename), path))
            if len(entries) >= MAX_LIST:
                entries.append(f"...[capped at {MAX_LIST} files]")
                return "\n".join(entries)
    return "\n".join(entries) or "(no files)"
