"""Example 10 — code intelligence toolset (tree-sitter: python/go/java/kotlin).

Runs fully offline: it writes small source fixtures to a temp dir and runs a
scripted agent that uses the AST tools against them.

    uv run --extra dev python examples/10_code_intelligence.py

Requires the code extra (in dev): ``pip install "toolloop[code]"``.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from toolloop import Agent, Status
from toolloop.codetools import CODE_TOOLS
from toolloop.testing import ScriptedProvider, final_answer, tool_call


def write_fixtures(root: Path) -> None:
    (root / "controller.py").write_text(
        "class UserController:\n"
        "    def index(self):\n"
        "        return []\n"
        "\n"
        "def register_routes(app):\n"
        "    app.add(UserController())\n"
    )
    java_dir = root / "com" / "example"
    java_dir.mkdir(parents=True)
    (java_dir / "UserController.java").write_text(
        "package com.example;\n"
        "\n"
        "@RestController\n"
        '@RequestMapping("/api/users")\n'
        "public class UserController {\n"
        "\n"
        '    @GetMapping("/{id}")\n'
        "    public User get(@PathVariable Long id) { return null; }\n"
        "}\n"
    )


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_fixtures(root)

        script = [
            tool_call("symbols", call_id="c1", path=str(root / "controller.py")),
            tool_call("find_symbol", call_id="c2", name="UserController", root=str(root)),
            tool_call("spring_endpoints", call_id="c3", root=str(root)),
            final_answer("mapped the code"),
        ]
        provider = ScriptedProvider(script)
        agent = Agent(provider, tools=CODE_TOOLS)
        result = await agent.run(f"explore the code at {root}")

        assert result.status is Status.COMPLETED
        for record in [call for step in result.history for call in step.calls]:
            print(f"{record.name}({record.args})")
            print("   " + record.result.replace("\n", "\n   "))
        print("status:", result.status.value)


if __name__ == "__main__":
    asyncio.run(main())
