"""``grep``: regex search across files, pure Python."""

from __future__ import annotations

import fnmatch
import os
import re

from .definition import tool
from .fs import SKIP_DIRS

MAX_MATCHES = 100


@tool
async def grep(pattern: str, path: str = ".", glob: str = "*", ignore_case: bool = False) -> str:
    """Search file contents with a regular expression; returns ``file:line: text`` matches."""
    try:
        regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        raise ValueError(f"invalid regex: {exc}") from None
    matches: list[str] = []
    root = os.path.abspath(path)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            if not fnmatch.fnmatch(filename, glob):
                continue
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, root)
            try:
                with open(full, "rb") as fh:
                    if b"\x00" in fh.read(1024):
                        continue  # skip binaries
                    fh.seek(0)
                    for lineno, raw_line in enumerate(fh, start=1):
                        try:
                            line = raw_line.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                        if regex.search(line):
                            matches.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(matches) >= MAX_MATCHES:
                                matches.append(f"...[capped at {MAX_MATCHES} matches]")
                                return "\n".join(matches)
            except OSError:
                continue
    return "\n".join(matches) or "(no matches)"
