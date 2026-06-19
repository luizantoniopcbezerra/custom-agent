from unittest.mock import MagicMock, patch

import pytest

from agent.domain.models import RepoConfig
from agent.infrastructure.github_client import GithubClient


def _make_label(name: str) -> MagicMock:
    lbl = MagicMock()
    lbl.name = name
    return lbl


def _make_issue(number: int, title: str, labels: list[str], is_pr: bool = False) -> MagicMock:
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = f"Body of issue {number}"
    issue.labels = [_make_label(lbl) for lbl in labels]
    issue.created_at.isoformat.return_value = "2026-06-01T00:00:00"
    issue.pull_request = MagicMock() if is_pr else None
    return issue


def _make_client_with_mocks() -> tuple[GithubClient, MagicMock]:
    """Return (client, mock_gh) with auth validation bypassed."""
    with patch("agent.infrastructure.github_client.Github") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_gh_cls.return_value = mock_gh
        mock_gh.get_user.return_value.login = "testuser"

        client = GithubClient(token="ghp_test")
        client._gh = mock_gh
    return client, mock_gh


def test_get_open_issues_returns_dicts(monkeypatch: pytest.MonkeyPatch) -> None:
    client, mock_gh = _make_client_with_mocks()

    repo_config = RepoConfig(owner="alice", name="repo")
    mock_repo = MagicMock()
    mock_repo.full_name = "alice/repo"
    mock_repo.get_label.return_value = MagicMock()
    issues = [_make_issue(1, "Fix bug", ["bug"]), _make_issue(2, "Add docs", [])]
    mock_repo.get_issues.return_value = iter(issues)
    mock_gh.get_repo.return_value = mock_repo

    result = client.get_open_issues(repo_config)

    assert len(result) == 2
    assert result[0]["number"] == 1
    assert result[0]["title"] == "Fix bug"
    assert "repo_full_name" in result[0]


def test_get_open_issues_excludes_prs() -> None:
    client, mock_gh = _make_client_with_mocks()

    repo_config = RepoConfig(owner="alice", name="repo")
    mock_repo = MagicMock()
    mock_repo.full_name = "alice/repo"
    mock_repo.get_issues.return_value = iter(
        [
            _make_issue(1, "Real issue", []),
            _make_issue(2, "Actually a PR", [], is_pr=True),
        ]
    )
    mock_gh.get_repo.return_value = mock_repo

    result = client.get_open_issues(repo_config)

    assert len(result) == 1
    assert result[0]["number"] == 1


def test_get_open_issues_filters_excluded_labels() -> None:
    client, mock_gh = _make_client_with_mocks()

    repo_config = RepoConfig(owner="alice", name="repo", exclude_labels=["wontfix"])
    mock_repo = MagicMock()
    mock_repo.full_name = "alice/repo"
    mock_repo.get_issues.return_value = iter(
        [
            _make_issue(1, "Good issue", ["bug"]),
            _make_issue(2, "Blocked issue", ["wontfix"]),
        ]
    )
    mock_gh.get_repo.return_value = mock_repo

    result = client.get_open_issues(repo_config)

    assert len(result) == 1
    assert result[0]["number"] == 1


def test_get_open_pr_url_returns_url_when_pr_exists() -> None:
    client, mock_gh = _make_client_with_mocks()

    mock_repo = MagicMock()
    mock_repo.full_name = "alice/repo"
    pr = MagicMock()
    pr.html_url = "https://github.com/alice/repo/pull/42"
    mock_gh.search_issues.return_value = iter([pr])

    result = client.get_open_pr_url(mock_repo, 42)

    assert result == "https://github.com/alice/repo/pull/42"


def test_get_open_pr_url_returns_none_when_no_pr() -> None:
    client, mock_gh = _make_client_with_mocks()

    mock_repo = MagicMock()
    mock_repo.full_name = "alice/repo"
    mock_gh.search_issues.return_value = iter([])

    assert client.get_open_pr_url(mock_repo, 99) is None


def test_open_pr_calls_create_pull_with_correct_params() -> None:
    client, mock_gh = _make_client_with_mocks()

    mock_repo = MagicMock()
    mock_repo.default_branch = "main"
    mock_repo.create_pull.return_value.html_url = "https://github.com/alice/repo/pull/1"

    client.open_pr(
        repo=mock_repo,
        branch_name="agent/issue-1-fix",
        issue_number=1,
        issue_title="Fix login bug",
        summary="Changed auth.py to handle edge case.",
    )

    mock_repo.create_pull.assert_called_once()
    call_kwargs = mock_repo.create_pull.call_args[1]
    assert call_kwargs["title"] == "fix: Fix login bug"
    assert call_kwargs["head"] == "agent/issue-1-fix"
    assert call_kwargs["base"] == "main"
    assert "Closes #1" in call_kwargs["body"]
