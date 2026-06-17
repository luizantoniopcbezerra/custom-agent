from unittest.mock import MagicMock, patch

import pytest
from git import GitCommandError

from agent.infrastructure.git_ops import (
    BranchAlreadyExistsError,
    _mask_token,
    cleanup,
    clone,
    commit_and_push,
)


def test_mask_token_replaces_token() -> None:
    url = "https://x-access-token:ghp_supersecret123@github.com/user/repo.git"
    masked = _mask_token(url)
    assert "ghp_supersecret123" not in masked
    assert "x-access-token:***@" in masked


def test_mask_token_leaves_non_token_url_unchanged() -> None:
    url = "https://github.com/user/repo.git"
    assert _mask_token(url) == url


def test_clone_does_not_log_token(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("agent.infrastructure.git_ops.Repo.clone_from") as mock_clone:
        mock_clone.return_value = MagicMock()
        clone("alice", "repo", "ghp_topsecret", "/tmp/test_repo")

    captured = capsys.readouterr()
    assert "ghp_topsecret" not in captured.out
    assert "ghp_topsecret" not in captured.err


def test_clone_calls_clone_from_with_token_url() -> None:
    with patch("agent.infrastructure.git_ops.Repo.clone_from") as mock_clone:
        mock_clone.return_value = MagicMock()
        clone("alice", "repo", "mytoken", "/tmp/dest")

    url_arg = mock_clone.call_args[0][0]
    assert "mytoken" in url_arg
    assert "alice/repo" in url_arg


def test_commit_and_push_sequence() -> None:
    mock_repo = MagicMock()
    mock_repo.git.checkout = MagicMock()
    mock_repo.git.add = MagicMock()
    mock_repo.index.commit = MagicMock()
    mock_remote = MagicMock()
    mock_repo.remote.return_value = mock_remote

    commit_and_push(mock_repo, "agent/issue-1-fix", "fix: patch issue 1")

    mock_repo.git.checkout.assert_called_once_with("-b", "agent/issue-1-fix")
    mock_repo.git.add.assert_called_once_with("-A")
    mock_repo.index.commit.assert_called_once_with("fix: patch issue 1")
    mock_remote.push.assert_called_once_with(refspec="HEAD:agent/issue-1-fix")


def test_commit_and_push_raises_branch_exists_on_checkout() -> None:
    mock_repo = MagicMock()
    mock_repo.git.checkout.side_effect = GitCommandError(
        "checkout", "fatal: a branch named 'agent/issue-1-fix' already exists"
    )

    with pytest.raises(BranchAlreadyExistsError):
        commit_and_push(mock_repo, "agent/issue-1-fix", "msg")


def test_cleanup_calls_close_before_rmtree(tmp_path: pytest.TempPathFactory) -> None:
    mock_repo = MagicMock()
    call_order: list[str] = []
    mock_repo.close.side_effect = lambda: call_order.append("close")

    with patch("agent.infrastructure.git_ops.shutil.rmtree") as mock_rmtree:
        mock_rmtree.side_effect = lambda *_args, **_kwargs: call_order.append("rmtree")
        cleanup(mock_repo, "/tmp/fake_dir")

    assert call_order == ["close", "rmtree"]
