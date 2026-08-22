from __future__ import annotations

from toolloop.tools import bash, edit_file, grep, list_files, read_file, write_file


async def test_fs_roundtrip(tmp_path):
    target = tmp_path / "sub" / "f.txt"
    ok, note = await write_file.execute({"path": str(target), "content": "hello\nworld"})
    assert ok and "11 chars" in note and "hello" not in note  # compact by design

    ok, body = await read_file.execute({"path": str(target)})
    assert ok and body.startswith("hello\nworld")

    ok, note = await edit_file.execute(
        {"path": str(target), "old_string": "world", "new_string": "toolloop"}
    )
    assert ok and "1 occurrence" in note
    ok, body = await read_file.execute({"path": str(target)})
    assert "toolloop" in body


async def test_edit_requires_unique_match(tmp_path):
    target = tmp_path / "dup.txt"
    target.write_text("aa\naa\n")
    ok, note = await edit_file.execute(
        {"path": str(target), "old_string": "aa", "new_string": "bb"}
    )
    assert not ok and "2 times" in note

    ok, note = await edit_file.execute(
        {"path": str(target), "old_string": "aa", "new_string": "bb", "replace_all": True}
    )
    assert ok and "2 occurrence" in note


async def test_read_file_limit_and_offset(tmp_path):
    target = tmp_path / "lines.txt"
    target.write_text("\n".join(f"line{i}" for i in range(10)))
    ok, body = await read_file.execute({"path": str(target), "offset": 2, "limit": 3})
    assert ok and "line2" in body and "line4" in body and "line5" not in body
    assert "lines 2..4 of 10" in body


async def test_list_files_pattern_and_skip(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.txt").write_text("y = 2")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("z")
    ok, out = await list_files.execute({"path": str(tmp_path), "pattern": "*.py"})
    assert ok and "a.py" in out and "b.txt" not in out
    ok, out = await list_files.execute({"path": str(tmp_path)})
    assert ok and "b.txt" in out and "junk.js" not in out


async def test_grep_matches_with_lineno(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 'needle here'\n")
    (tmp_path / "b.txt").write_text("nothing relevant")
    ok, out = await grep.execute({"pattern": "needle", "path": str(tmp_path)})
    assert ok and "a.py:2:" in out and "b.txt" not in out

    ok, out = await grep.execute({"pattern": "NEEDLE", "path": str(tmp_path)})
    assert "(no matches)" in out

    ok, out = await grep.execute({"pattern": "NEEDLE", "path": str(tmp_path), "ignore_case": True})
    assert "a.py:2:" in out


async def test_grep_invalid_regex(tmp_path):
    ok, out = await grep.execute({"pattern": "([", "path": str(tmp_path)})
    assert not ok and "invalid regex" in out


async def test_bash_runs_and_reports_exit_code():
    ok, out = await bash.execute({"command": "echo hi"})
    assert ok and "exit code: 0" in out and "hi" in out


async def test_bash_nonzero_exit(tmp_path):
    ok, out = await bash.execute({"command": "printf 'boom' >&2; exit 3"})
    assert ok  # executed fine; failure is part of the observation
    assert "exit code: 3" in out and "boom" in out
