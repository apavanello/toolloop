"""Code-intelligence toolset (extra: ``toolloop[code]``).

AST-powered tools for python, go, java and kotlin (tree-sitter), plus
Spring-aware JVM discovery — with a generic surface: the language is
detected from the file extension, so one small toolset serves them all.

    pip install "toolloop[code]"

    from toolloop.codetools import CODE_TOOLS  # = STD_TOOLS + AST_TOOLS
    agent = Agent(provider, tools=CODE_TOOLS)
"""

from __future__ import annotations

from ..tools import STD_TOOLS
from .tools import (
    AST_TOOLS,
    find_symbol,
    imports,
    references,
    spring_beans,
    spring_endpoints,
    symbols,
)

CODE_TOOLS = [*STD_TOOLS, *AST_TOOLS]

__all__ = [
    "AST_TOOLS",
    "CODE_TOOLS",
    "symbols",
    "find_symbol",
    "references",
    "imports",
    "spring_endpoints",
    "spring_beans",
]
