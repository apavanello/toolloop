"""toolloop CLI: scaffold agent projects (``init``) and validate them (``check``)."""

from __future__ import annotations

import argparse
import importlib
import sys
import tomllib
from pathlib import Path
from typing import Any

from . import __version__
from .protocol.json_protocol import JsonToolProtocol
from .tools.definition import ToolDefinition

TOOLLOOP_SECTION = """\
[tool.toolloop]
# modules whose tool definitions `toolloop check` should validate
modules = ["my_tools"]
# module that builds/exports your Agent (checked for importability)
agent = "agent"
"""

FULL_PYPROJECT_TEMPLATE = (
    """\
[project]
name = "my-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["toolloop>=0.2"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

"""
    + TOOLLOOP_SECTION
)

MINIMAL_PYPROJECT_TEMPLATE = (
    """\
[project]
name = "my-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["toolloop>=0.2"]

"""
    + TOOLLOOP_SECTION
)

AGENT_TEMPLATE = '''\
"""Your toolloop agent.

The scripted provider below runs offline; swap it for your real one
(see toolloop's examples/providers for ready-made adapters).
"""

from __future__ import annotations

from toolloop import Agent
from toolloop.testing import ScriptedProvider

from my_tools import look_up

agent = Agent(
    ScriptedProvider(
        [
            '{"type": "tool_call", "calls": '
            '[{"id": "c1", "name": "look_up", "args": {"key": "pypi"}}]}',
            '{"type": "final_answer", "output": "found it"}',
        ]
    ),
    tools=[look_up],
    # system_prompt="You are ...",
)
'''

TOOLS_TEMPLATE = '''\
"""Your tools: async functions decorated with @tool.

Name and description come from the function; the argument schema comes
from the type hints (validated with pydantic).
"""

from __future__ import annotations

from toolloop import tool


@tool
async def look_up(key: str) -> str:
    """Look up a key in the catalog."""
    return f"{key}=found"
'''

SCENARIO_TEST_TEMPLATE = '''\
"""Deterministic scenario test — no LLM, no network, no flakes."""

from toolloop import Agent
from toolloop.testing import ScriptedProvider, final_answer, tool_call

from my_tools import look_up


async def test_agent_completes():
    provider = ScriptedProvider(
        [tool_call("look_up", call_id="c1", key="pypi"), final_answer("found it")]
    )
    result = await Agent(provider, tools=[look_up]).run("look up pypi")
    assert result.output == "found it"
    assert result.history[0].calls[0].status == "ok"
'''

EXISTING_PROJECT_TEST_TEMPLATE = '''\
"""Deterministic scenario test scaffold — adapt to YOUR tools and agent."""

from toolloop import Agent, tool
from toolloop.testing import ScriptedProvider, final_answer, tool_call


@tool
async def sample(value: str) -> str:
    """A sample tool to prove the wiring."""
    return f"got {value}"


async def test_agent_completes():
    provider = ScriptedProvider(
        [tool_call("sample", call_id="c1", value="x"), final_answer("done")]
    )
    result = await Agent(provider, tools=[sample]).run("go")
    assert result.output == "done"
'''

README_TEMPLATE = """\
# my-agent

An agent built with [toolloop](https://github.com/apavanello/toolloop).

- `agent.py` — the agent (scripted provider demo; swap for your real one)
- `my_tools.py` — your tools (`@tool` async functions)
- `tests/test_agent.py` — deterministic scenario test (no LLM needed)

Validate any time with: `toolloop check`
"""

GITIGNORE_TEMPLATE = """\
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="toolloop",
        description="Scaffold and validate toolloop agent projects.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="scaffold toolloop project files (never overwrites anything)"
    )
    init_parser.add_argument("path", nargs="?", default=".", type=Path)

    check_parser = subparsers.add_parser(
        "check", help="validate the tools/agent declared in [tool.toolloop]"
    )
    check_parser.add_argument("path", nargs="?", default=".", type=Path)

    args = parser.parse_args(argv)
    if args.command == "init":
        return cmd_init(args.path)
    return cmd_check(args.path)


def cmd_init(path: Path) -> int:
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    actions: list[str] = []

    if not any(path.iterdir()):  # empty folder: full scaffold
        _write_if_missing(path / "pyproject.toml", FULL_PYPROJECT_TEMPLATE, actions)
        _write_if_missing(path / "agent.py", AGENT_TEMPLATE, actions)
        _write_if_missing(path / "my_tools.py", TOOLS_TEMPLATE, actions)
        _write_if_missing(path / "tests/test_agent.py", SCENARIO_TEST_TEMPLATE, actions)
        _write_if_missing(path / "README.md", README_TEMPLATE, actions)
        _write_if_missing(path / ".gitignore", GITIGNORE_TEMPLATE, actions)
    else:  # existing project: only the missing toolloop pieces
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            if "[tool.toolloop]" in pyproject.read_text():
                actions.append("kept existing pyproject.toml ([tool.toolloop] present)")
            else:
                _append_section(pyproject, TOOLLOOP_SECTION, actions)
        else:
            _write_if_missing(pyproject, MINIMAL_PYPROJECT_TEMPLATE, actions)
        if not (path / "tests").exists():
            _write_if_missing(path / "tests/test_agent.py", EXISTING_PROJECT_TEST_TEMPLATE, actions)
        else:
            actions.append("kept existing tests/")

    for action in actions:
        print(action)
    print(f"done ({path})")
    return 0


def cmd_check(path: Path) -> int:
    path = path.resolve()
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        print("error: no pyproject.toml found — run `toolloop init` first", file=sys.stderr)
        return 1
    try:
        config: dict[str, Any] = tomllib.loads(pyproject.read_text())
    except tomllib.TOMLDecodeError as exc:
        print(f"error: pyproject.toml is not valid TOML: {exc}", file=sys.stderr)
        return 1

    section = config.get("tool", {}).get("toolloop", {})
    modules: list[str] = section.get("modules", [])
    agent_module: str | None = section.get("agent")
    if not modules and not agent_module:
        print("error: [tool.toolloop] declares nothing (set 'modules' and/or 'agent')")
        return 1

    failures: list[str] = []
    tools: list[ToolDefinition] = []
    sys.path.insert(0, str(path))
    try:
        for module_name in modules:
            try:
                module = importlib.import_module(module_name)
            except Exception as exc:
                failures.append(f"module {module_name!r}: import failed: {exc}")
                continue
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, ToolDefinition):
                    tools.append(attr)
        if agent_module:
            try:
                importlib.import_module(agent_module)
            except Exception as exc:
                failures.append(f"agent module {agent_module!r}: import failed: {exc}")
    finally:
        sys.path.remove(str(path))
        for name in [*modules, agent_module]:
            if name:
                sys.modules.pop(name, None)

    seen: set[str] = set()
    for tool_ in tools:
        if tool_.name in seen:
            failures.append(f"duplicate tool name: {tool_.name!r}")
        seen.add(tool_.name)
    try:
        JsonToolProtocol().render_instructions(tools)
    except Exception as exc:
        failures.append(f"could not render tool instructions: {exc}")

    print(f"tools: {len(tools)}")
    for tool_ in tools:
        args_count = len(tool_.args_model.model_fields)
        flag = " [dangerous]" if tool_.dangerous else ""
        print(f"  {tool_.name:<24} args={args_count}{flag}")
    if agent_module and not any(f.startswith("agent module") for f in failures):
        print(f"agent module {agent_module!r}: imports OK")
    if not tools:
        print("warning: no tools found in the declared modules")
    if failures:
        print("\nproblems:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("check passed")
    return 0


def _write_if_missing(target: Path, content: str, actions: list[str]) -> None:
    if target.exists():
        actions.append(f"kept existing {target.name} (not overwritten)")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    actions.append(f"created {target}")


def _append_section(pyproject: Path, section: str, actions: list[str]) -> None:
    current = pyproject.read_text()
    pyproject.write_text(current.rstrip("\n") + "\n\n" + section)
    actions.append("added [tool.toolloop] to existing pyproject.toml")


if __name__ == "__main__":
    sys.exit(main())
