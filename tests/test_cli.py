from __future__ import annotations

from pathlib import Path

from toolloop.cli import main


def test_init_empty_folder_scaffolds_everything(tmp_path: Path):
    project = tmp_path / "agent-project"
    assert main(["init", str(project)]) == 0
    for name in ("pyproject.toml", "agent.py", "my_tools.py", "README.md", ".gitignore"):
        assert (project / name).exists(), name
    assert (project / "tests" / "test_agent.py").exists()
    assert "[tool.toolloop]" in (project / "pyproject.toml").read_text()


def test_init_never_overwrites(tmp_path: Path):
    project = tmp_path / "p"
    assert main(["init", str(project)]) == 0
    pyproject_before = (project / "pyproject.toml").read_text()
    (project / "agent.py").write_text("# customized by the user\n")

    assert main(["init", str(project)]) == 0
    assert (project / "pyproject.toml").read_text() == pyproject_before
    assert (project / "agent.py").read_text() == "# customized by the user\n"


def test_init_existing_project_adds_only_metadata(tmp_path: Path):
    project = tmp_path / "p"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "existing"\n')
    (project / "app.py").write_text("print('hi')\n")

    assert main(["init", str(project)]) == 0
    pyproject = (project / "pyproject.toml").read_text()
    assert '[project]\nname = "existing"' in pyproject  # original content intact
    assert "[tool.toolloop]" in pyproject  # section appended
    assert not (project / "agent.py").exists()  # no code files touched
    assert (project / "tests" / "test_agent.py").exists()  # tests scaffolded


def test_check_passes_on_fresh_scaffold(tmp_path: Path):
    project = tmp_path / "p"
    assert main(["init", str(project)]) == 0
    assert main(["check", str(project)]) == 0


def test_check_fails_on_broken_module(tmp_path: Path):
    project = tmp_path / "p"
    main(["init", str(project)])
    (project / "my_tools.py").write_text("import module_that_does_not_exist\n")
    assert main(["check", str(project)]) == 1


def test_check_fails_without_pyproject(tmp_path: Path):
    project = tmp_path / "empty"
    project.mkdir()
    assert main(["check", str(project)]) == 1


def test_check_fails_on_duplicate_tool_names(tmp_path: Path):
    project = tmp_path / "p"
    main(["init", str(project)])
    (project / "my_tools.py").write_text(
        "from toolloop import tool\n"
        "\n"
        "\n"
        "@tool\n"
        "async def first() -> str:\n"
        '    """One."""\n'
        '    return "a"\n'
        "\n"
        "\n"
        "@tool(name='first')\n"
        "async def second() -> str:\n"
        '    """Two with a colliding name."""\n'
        '    return "b"\n'
    )
    assert main(["check", str(project)]) == 1
