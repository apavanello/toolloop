from __future__ import annotations

import pytest

from toolloop.codetools import (
    AST_TOOLS,
    CODE_TOOLS,
    find_symbol,
    imports,
    references,
    spring_beans,
    spring_endpoints,
    symbols,
)
from toolloop.codetools._engine import SUPPORTED
from toolloop.tools import STD_TOOLS

PY = '''
import os
from typing import List

class Greeter:
    """Greets people."""

    def greet(self, name: str) -> str:
        return "hi " + name

def top_level(a, b=2):
    return a + b
'''

GO = """
package main

import (
    "fmt"
    "strings"
)

type Reader struct {
    Name string
}

type Shape interface {
    Area() float64
}

func (r *Reader) Read() int { return 0 }

func main() {
    fmt.Println(strings.ToUpper("x"))
}
"""

JAVA = """
package com.example;

import java.util.List;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping("/{id}")
    public User get(@PathVariable Long id) { return null; }

    @PostMapping("/admin")
    public User create(@RequestBody User user) { return user; }
}
"""

KOTLIN = """
package com.example

import org.springframework.stereotype.Service

@Service
class UserService {
    fun find(id: Long): User = repo.find(id)
}

@Configuration
class AppConfig {
    @Bean
    fun meter(): Meter = Meter()
}
"""


async def _run(tool, **args):
    ok, result = await tool.execute(args)
    assert ok, result
    return result


async def test_symbols_python(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(PY)
    outline = await _run(symbols, path=str(target))

    assert "class      Greeter" in outline
    assert "function   Greeter.greet" in outline
    assert "function   top_level" in outline


async def test_symbols_go(tmp_path):
    target = tmp_path / "main.go"
    target.write_text(GO)
    outline = await _run(symbols, path=str(target))

    assert "struct     Reader" in outline
    assert "interface  Shape" in outline
    assert "method     Reader.Read" in outline or "method     Read" in outline
    assert "function   main" in outline


async def test_symbols_java_and_kotlin(tmp_path):
    java = tmp_path / "UserController.java"
    java.write_text(JAVA)
    kotlin = tmp_path / "UserService.kt"
    kotlin.write_text(KOTLIN)

    java_outline = await _run(symbols, path=str(java))
    assert "class      UserController" in java_outline
    assert "method     UserController.get" in java_outline

    kotlin_outline = await _run(symbols, path=str(kotlin))
    assert "class      UserService" in kotlin_outline
    assert "function   UserService.find" in kotlin_outline


async def test_imports_per_language(tmp_path):
    py_file = tmp_path / "m.py"
    py_file.write_text(PY)
    go_file = tmp_path / "m.go"
    go_file.write_text(GO)
    java_file = tmp_path / "M.java"
    java_file.write_text(JAVA)

    assert "import os" in await _run(imports, path=str(py_file))
    assert "from typing import List" in await _run(imports, path=str(py_file))

    go_imports = await _run(imports, path=str(go_file))
    assert '"fmt"' in go_imports and '"strings"' in go_imports

    java_imports = await _run(imports, path=str(java_file))
    assert "package com.example" in java_imports
    assert "import java.util.List" in java_imports


async def test_find_symbol_across_files(tmp_path):
    (tmp_path / "a.py").write_text(PY)
    other = tmp_path / "b.py"
    other.write_text("class Greeter:\n    pass\n")
    (tmp_path / "ignored.txt").write_text("class Greeter:\n")  # not source

    result = await _run(find_symbol, name="Greeter", root=str(tmp_path))
    assert "a.py:" in result and "b.py:" in result
    assert "ignored.txt" not in result

    only_class = await _run(find_symbol, name="Greeter", root=str(tmp_path), kind="class")
    assert "a.py:" in only_class and "b.py:" in only_class

    missing = await _run(find_symbol, name="DoesNotExist", root=str(tmp_path))
    assert "no definitions" in missing


async def test_references_exclude_definition(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "def helper():\n    return 1\n\ndef caller():\n    return helper() + helper()\n"
    )
    result = await _run(references, symbol="helper", root=str(tmp_path))
    # definition (line 1) excluded; two usages on line 5
    assert "mod.py:5" in result
    assert "mod.py:1" not in result


async def test_spring_endpoints_java(tmp_path):
    (tmp_path / "UserController.java").write_text(JAVA)
    result = await _run(spring_endpoints, root=str(tmp_path))

    assert "GET" in result and "/api/users/{id}" in result
    assert "POST" in result and "/api/users/admin" in result
    assert "UserController.get" in result
    assert "UserController.create" in result


async def test_spring_beans_kotlin(tmp_path):
    (tmp_path / "UserService.kt").write_text(KOTLIN)
    result = await _run(spring_beans, root=str(tmp_path))

    assert "@Service" in result and "UserService" in result
    assert "@Bean" in result and "AppConfig.meter" in result


async def test_unsupported_extension_is_a_clear_error(tmp_path):
    target = tmp_path / "data.rb"
    target.write_text("puts 'oi'")
    ok, result = await symbols.execute({"path": str(target)})
    assert not ok
    assert "unsupported language" in result
    assert "kotlin" in result and SUPPORTED in result


def test_code_tools_composition():
    assert len(CODE_TOOLS) == len(STD_TOOLS) + len(AST_TOOLS)
    assert {t.name for t in STD_TOOLS} < {t.name for t in CODE_TOOLS}
    assert {t.name for t in AST_TOOLS} == {
        "symbols",
        "find_symbol",
        "references",
        "imports",
        "spring_endpoints",
        "spring_beans",
    }


def test_missing_extra_message(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("tree_sitter"):
            raise ImportError(f"No module named {name!r}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match=r"toolloop\[code\]"):
        import importlib

        import toolloop.codetools._engine as engine

        importlib.reload(engine)
