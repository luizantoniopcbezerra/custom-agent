"""Integration tests for the agentic loop using only the real filesystem (no GitHub, no network)."""

import json
import os
from unittest.mock import MagicMock

import pytest

from agent.domain.agentic_loop import run
from agent.domain.models import IssueCandidate


def _make_issue() -> IssueCandidate:
    return IssueCandidate(
        number=7,
        title="Fix greeting message",
        body="The greeting should say 'Hello' not 'Hi'.",
        score=1,
        reason="trivial",
        repo_full_name="alice/repo",
        created_at="2026-01-01T00:00:00",
    )


def _make_tool_call(name: str, args: dict) -> MagicMock:
    tc = MagicMock()
    tc.id = f"call_{name}_{hash(frozenset(args.items()))}"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _make_llm_response(tool_calls: list | None, content: str = "") -> MagicMock:
    msg = MagicMock()
    msg.tool_calls = tool_calls or None
    msg.content = content
    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    return resp


@pytest.fixture()
def repo_dir(tmp_path: pytest.TempPathFactory) -> str:
    """Temporary directory with three Python files simulating a real repo."""
    root = str(tmp_path)
    (tmp_path / "app.py").write_text("def greet():\n    return 'Hi'\n")  # type: ignore[union-attr]
    (tmp_path / "utils.py").write_text("def trim(s):\n    return s.strip()\n")  # type: ignore[union-attr]
    (tmp_path / "README.md").write_text("# My Project\n")  # type: ignore[union-attr]
    return root


def test_written_file_exists_on_disk(repo_dir: str) -> None:
    """LLM writes app.py on turn 1, stops on turn 2 — file must exist with correct content."""
    fixed_content = "def greet():\n    return 'Hello'\n"
    tc = _make_tool_call("write_file", {"path": "app.py", "content": fixed_content})
    client = MagicMock()
    client.chat.side_effect = [
        _make_llm_response([tc]),
        _make_llm_response(None, "Done."),
    ]

    written = run(_make_issue(), "", [], client, repo_dir, max_calls=10, max_file_bytes=50_000)

    assert written == ["app.py"]
    abs_path = os.path.join(repo_dir, "app.py")
    assert os.path.exists(abs_path)
    with open(abs_path) as fh:
        assert fh.read() == fixed_content


def test_written_files_matches_disk(repo_dir: str) -> None:
    """written_files returned by loop corresponds exactly to files on disk."""
    tc1 = _make_tool_call("write_file", {"path": "app.py", "content": "# v2"})
    tc2 = _make_tool_call("write_file", {"path": "utils.py", "content": "# v2"})
    client = MagicMock()
    client.chat.side_effect = [
        _make_llm_response([tc1, tc2]),
        _make_llm_response(None, "All done."),
    ]

    written = run(_make_issue(), "", [], client, repo_dir, max_calls=10, max_file_bytes=50_000)

    assert set(written) == {"app.py", "utils.py"}
    for path in written:
        assert os.path.exists(os.path.join(repo_dir, path))


def test_path_traversal_blocked(repo_dir: str) -> None:
    """LLM attempts to write outside root — file must not be created, written_files stays empty."""
    parent_evil = os.path.join(os.path.dirname(repo_dir), "evil.txt")
    tc = _make_tool_call("write_file", {"path": "../../evil.txt", "content": "pwned"})
    client = MagicMock()
    client.chat.side_effect = [
        _make_llm_response([tc]),
        _make_llm_response(None, "Done."),
    ]

    written = run(_make_issue(), "", [], client, repo_dir, max_calls=10, max_file_bytes=50_000)

    assert written == []
    assert not os.path.exists(parent_evil)


def test_loop_stops_at_max_calls_without_exception(repo_dir: str) -> None:
    """LLM never stops emitting tool_calls — loop must exit at max_calls=3 without raising."""
    tc = _make_tool_call("list_dir", {"path": "."})
    client = MagicMock()
    client.chat.side_effect = [_make_llm_response([tc]) for _ in range(3)]

    written = run(_make_issue(), "", [], client, repo_dir, max_calls=3, max_file_bytes=50_000)

    assert client.chat.call_count == 3
    assert written == []
