import json
from unittest.mock import MagicMock

import pytest

from agent.domain.agentic_loop import _build_initial_user_message, _process_tool_calls, run
from agent.domain.models import IssueCandidate


def _make_issue() -> IssueCandidate:
    return IssueCandidate(
        number=1,
        title="Fix login bug",
        body="Users cannot log in after password reset.",
        score=2,
        reason="small fix",
        repo_full_name="alice/repo",
        created_at="2026-01-01T00:00:00",
    )


def _make_tool_call(name: str, args: dict) -> MagicMock:
    tc = MagicMock()
    tc.id = f"call_{name}"
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


def _make_llm_client(responses: list) -> MagicMock:
    client = MagicMock()
    client.chat.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# _build_initial_user_message
# ---------------------------------------------------------------------------


def test_build_initial_user_message_includes_issue_title() -> None:
    issue = _make_issue()
    msg = _build_initial_user_message(issue, "app.py\nutils.py", [])
    assert "Fix login bug" in msg
    assert "Issue #1" in msg


def test_build_initial_user_message_includes_file_tree() -> None:
    issue = _make_issue()
    msg = _build_initial_user_message(issue, "app.py\nutils.py", [])
    assert "app.py" in msg
    assert "utils.py" in msg


def test_build_initial_user_message_includes_relevant_files() -> None:
    issue = _make_issue()
    msg = _build_initial_user_message(issue, "", [("app.py", "def login(): pass")])
    assert "def login(): pass" in msg


# ---------------------------------------------------------------------------
# _process_tool_calls
# ---------------------------------------------------------------------------


def test_process_tool_calls_returns_tool_role_messages(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    tc = _make_tool_call("list_dir", {"path": "."})
    results = _process_tool_calls([tc], root, [], max_bytes=4096)
    assert len(results) == 1
    assert results[0]["role"] == "tool"
    assert results[0]["tool_call_id"] == "call_list_dir"


def test_process_tool_calls_all_processed_in_one_turn(
    tmp_path: pytest.TempPathFactory,
) -> None:
    root = str(tmp_path)
    tc1 = _make_tool_call("list_dir", {"path": "."})
    tc2 = _make_tool_call("read_file", {"path": "nonexistent.py"})
    results = _process_tool_calls([tc1, tc2], root, [], max_bytes=4096)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# run — termination conditions
# ---------------------------------------------------------------------------


def test_run_terminates_on_no_tool_calls(tmp_path: pytest.TempPathFactory) -> None:
    """LLM writes a file on turn 1, returns no tool calls on turn 2 → loop exits."""
    root = str(tmp_path)
    write_tc = _make_tool_call("write_file", {"path": "app.py", "content": "# fixed"})
    responses = [
        _make_llm_response([write_tc]),
        _make_llm_response(None, "Done."),
    ]
    client = _make_llm_client(responses)
    issue = _make_issue()

    written = run(issue, "", [], client, root, max_calls=10, max_file_bytes=50_000)

    assert written == ["app.py"]
    assert client.chat.call_count == 2


def test_run_terminates_at_budget(tmp_path: pytest.TempPathFactory) -> None:
    """LLM keeps returning tool_calls — loop stops at max_calls without exception."""
    root = str(tmp_path)
    tc = _make_tool_call("list_dir", {"path": "."})
    # All 5 turns return tool_calls — loop must stop at max_calls=5
    responses = [_make_llm_response([tc]) for _ in range(5)]
    client = _make_llm_client(responses)
    issue = _make_issue()

    written = run(issue, "", [], client, root, max_calls=5, max_file_bytes=50_000)

    assert client.chat.call_count == 5
    assert written == []


def test_run_processes_multiple_tool_calls_per_turn(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Two tool calls in one turn — both dispatched before next LLM call."""
    root = str(tmp_path)
    tc1 = _make_tool_call("write_file", {"path": "a.py", "content": "pass"})
    tc2 = _make_tool_call("write_file", {"path": "b.py", "content": "pass"})
    responses = [
        _make_llm_response([tc1, tc2]),
        _make_llm_response(None, "Done."),
    ]
    client = _make_llm_client(responses)
    issue = _make_issue()

    written = run(issue, "", [], client, root, max_calls=10, max_file_bytes=50_000)

    assert set(written) == {"a.py", "b.py"}
    assert client.chat.call_count == 2


def test_run_arguments_are_json_loaded_not_passed_as_string(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """dispatch_tool must json.loads(arguments) — this test verifies the file is actually
    written (not silently failed by passing a string where a dict is expected)."""
    root = str(tmp_path)
    tc = _make_tool_call("write_file", {"path": "test.py", "content": "hello"})
    responses = [
        _make_llm_response([tc]),
        _make_llm_response(None, "Done."),
    ]
    client = _make_llm_client(responses)
    issue = _make_issue()

    written = run(issue, "", [], client, root, max_calls=10, max_file_bytes=50_000)

    assert "test.py" in written


def test_run_returns_empty_list_when_no_writes(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    responses = [_make_llm_response(None, "Nothing to do.")]
    client = _make_llm_client(responses)
    issue = _make_issue()

    written = run(issue, "", [], client, root, max_calls=10, max_file_bytes=50_000)

    assert written == []
    assert client.chat.call_count == 1
