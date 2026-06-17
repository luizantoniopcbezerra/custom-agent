import json
import os
from unittest.mock import MagicMock

import pytest

from agent.domain.tools import (
    TOOL_SCHEMAS,
    _guard_path,
    dispatch_tool,
    list_dir,
    read_file,
    write_file,
)

# ---------------------------------------------------------------------------
# Security: path traversal guard
# ---------------------------------------------------------------------------


def test_guard_path_traversal_rejected(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    result = _guard_path("../../etc/passwd", root)
    assert result is None


def test_guard_path_absolute_rejected(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    # os.path.join with absolute path discards the prefix — realpath check catches it
    result = _guard_path("/etc/passwd", root)
    assert result is None


def test_guard_path_null_byte_rejected(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    result = _guard_path("file\x00.py", root)
    assert result is None


def test_guard_path_valid_inside_root(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    with open(os.path.join(root, "main.py"), "w") as fh:
        fh.write("pass")
    result = _guard_path("main.py", root)
    assert result is not None
    assert result.startswith(os.path.realpath(root))


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


def test_read_file_traversal_returns_error(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    result = read_file("../../etc/passwd", root, max_bytes=4096)
    assert result.startswith("ERROR:")


def test_read_file_valid_returns_content(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    with open(os.path.join(root, "hello.txt"), "w") as fh:
        fh.write("hello world")
    result = read_file("hello.txt", root, max_bytes=4096)
    assert result == "hello world"


def test_read_file_missing_returns_error(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    result = read_file("nonexistent.py", root, max_bytes=4096)
    assert result.startswith("ERROR:")


def test_read_file_respects_max_bytes(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    with open(os.path.join(root, "big.txt"), "w") as fh:
        fh.write("x" * 1000)
    result = read_file("big.txt", root, max_bytes=50)
    assert len(result) == 50


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


def test_write_file_traversal_returns_error_no_file_created(
    tmp_path: pytest.TempPathFactory,
) -> None:
    root = str(tmp_path)
    written: list[str] = []
    result = write_file("../../evil.txt", "bad content", root, written)
    assert result.startswith("ERROR:")
    assert written == []
    assert not os.path.exists("/tmp/evil.txt")


def test_write_file_creates_intermediate_dirs(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    written: list[str] = []
    result = write_file("deep/nested/file.py", "print('hi')", root, written)
    assert result == "ok"
    assert os.path.exists(os.path.join(root, "deep", "nested", "file.py"))
    assert "deep/nested/file.py" in written


def test_write_file_adds_to_written_files(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    written: list[str] = []
    write_file("a.py", "pass", root, written)
    write_file("b.py", "pass", root, written)
    assert len(written) == 2


def test_write_file_absolute_path_rejected(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    written: list[str] = []
    result = write_file("/etc/passwd", "bad", root, written)
    assert result.startswith("ERROR:")
    assert written == []


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


def test_list_dir_returns_json(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    with open(os.path.join(root, "file.py"), "w") as fh:
        fh.write("pass")
    result = list_dir(".", root)
    entries = json.loads(result)
    names = [e["name"] for e in entries]
    assert "file.py" in names


def test_list_dir_traversal_returns_error(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    result = list_dir("../../etc", root)
    assert result.startswith("ERROR:")


# ---------------------------------------------------------------------------
# dispatch_tool
# ---------------------------------------------------------------------------


def test_dispatch_tool_unknown_name_returns_error(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    tool_call = MagicMock()
    tool_call.function.name = "delete_everything"
    tool_call.function.arguments = json.dumps({})
    result = dispatch_tool(tool_call, root, [], max_bytes=4096)
    assert result.startswith("ERROR:")


def test_dispatch_tool_routes_read_file(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    with open(os.path.join(root, "x.py"), "w") as fh:
        fh.write("content here")
    tool_call = MagicMock()
    tool_call.function.name = "read_file"
    tool_call.function.arguments = json.dumps({"path": "x.py"})
    result = dispatch_tool(tool_call, root, [], max_bytes=4096)
    assert result == "content here"


def test_dispatch_tool_routes_write_file(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    written: list[str] = []
    tool_call = MagicMock()
    tool_call.function.name = "write_file"
    tool_call.function.arguments = json.dumps({"path": "out.py", "content": "pass"})
    result = dispatch_tool(tool_call, root, written, max_bytes=4096)
    assert result == "ok"
    assert "out.py" in written


def test_guard_path_symlink_outside_root_rejected(tmp_path: pytest.TempPathFactory) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    link = repo / "link.txt"
    os.symlink(outside, link)
    result = _guard_path("link.txt", str(repo))
    assert result is None


def test_list_dir_truncates_at_200_entries(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    for i in range(201):
        with open(os.path.join(root, f"file_{i:04d}.txt"), "w") as fh:
            fh.write("")
    result = list_dir(".", root)
    entries = json.loads(result)
    assert len(entries) == 200


# ---------------------------------------------------------------------------
# TOOL_SCHEMAS
# ---------------------------------------------------------------------------


def test_tool_schemas_structure() -> None:
    assert len(TOOL_SCHEMAS) == 3
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}  # type: ignore[index]
    assert names == {"read_file", "write_file", "list_dir"}
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert "description" in schema["function"]  # type: ignore[index]
        assert "parameters" in schema["function"]  # type: ignore[index]
