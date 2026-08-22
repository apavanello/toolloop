"""Tools: the ``@tool`` decorator plus an optional coding-agent toolset."""

from .definition import ToolDefinition, tool
from .fs import edit_file, list_files, read_file, write_file
from .search import grep
from .shell import bash

STD_TOOLS = [bash, read_file, write_file, edit_file, list_files, grep]

__all__ = [
    "ToolDefinition",
    "tool",
    "STD_TOOLS",
    "bash",
    "read_file",
    "write_file",
    "edit_file",
    "list_files",
    "grep",
]
