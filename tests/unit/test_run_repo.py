from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.application.run_repo import RunRepoDeps, _slugify, run_for_repo
from agent.config import AgentConfig, AgentSettings, OpenRouterConfig
from agent.domain.models import IssueCandidate, RepoConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(number: int = 1, score: int = 2) -> IssueCandidate:
    return IssueCandidate(
        number=number,
        title="Fix login bug",
        body="Users cannot log in.",
        score=score,
        reason="heuristic",
        repo_full_name="alice/repo",
        created_at="2026-01-01T00:00:00",
    )


def _make_config(dry_run: bool = False) -> AgentConfig:
    return AgentConfig.model_construct(
        openrouter_api_key="sk-test",
        gh_token="ghp_test",
        dry_run=dry_run,
        openrouter=OpenRouterConfig(),
        agent=AgentSettings(),
        repos=[],
    )


def _make_deps(dry_run: bool = False) -> RunRepoDeps:
    config = _make_config(dry_run=dry_run)
    return RunRepoDeps(
        github_client=MagicMock(),
        llm_client=MagicMock(),
        config=config,
    )


def _make_repo_config() -> RepoConfig:
    return RepoConfig(owner="alice", name="repo")


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert _slugify("Fix Login Bug") == "fix-login-bug"


def test_slugify_special_chars() -> None:
    slug = _slugify("Fix: user/auth & session (timeout)")
    assert "/" not in slug
    assert " " not in slug
    assert slug.startswith("fix")


def test_slugify_truncates_at_50() -> None:
    long_title = "a" * 100
    assert len(_slugify(long_title)) <= 50


# ---------------------------------------------------------------------------
# run_for_repo — noop: no open issues
# ---------------------------------------------------------------------------


def test_noop_when_no_open_issues() -> None:
    deps = _make_deps()
    deps.github_client.get_open_issues.return_value = []

    results = run_for_repo(_make_repo_config(), deps)

    assert len(results) == 1
    assert results[0].status == "noop"
    assert results[0].issue is None


# ---------------------------------------------------------------------------
# run_for_repo — noop: no linked branch
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.score_issues")
def test_noop_when_no_linked_branch(mock_score_issues: MagicMock) -> None:
    deps = _make_deps()
    issue = _make_issue()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Fix login bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = [issue]
    deps.github_client.get_linked_branch.return_value = None

    results = run_for_repo(_make_repo_config(), deps)

    assert len(results) == 1
    assert results[0].status == "noop"


# ---------------------------------------------------------------------------
# run_for_repo — pending PR already exists
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.score_issues")
def test_pending_pr_when_pr_already_exists(mock_score_issues: MagicMock) -> None:
    deps = _make_deps()
    issue = _make_issue()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Fix login bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = [issue]
    deps.github_client.get_linked_branch.return_value = "fix/1-fix-login-bug"
    deps.github_client.get_open_pr_url.return_value = "https://github.com/alice/repo/pull/42"

    results = run_for_repo(_make_repo_config(), deps)

    assert any(r.status == "pending_pr" for r in results)


# ---------------------------------------------------------------------------
# run_for_repo — success with dry_run
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.run_sprint")
@patch("agent.application.run_repo.build_file_tree", return_value="app.py")
@patch("agent.application.run_repo.extract_keywords", return_value=["login"])
@patch("agent.application.run_repo.select_relevant_files", return_value=[])
@patch("agent.application.run_repo.score_issues")
def test_success_dry_run_skips_commit(
    mock_score_issues: MagicMock,
    mock_select_rel: MagicMock,
    mock_keywords: MagicMock,
    mock_tree: MagicMock,
    mock_sprint: MagicMock,
    mock_clone: MagicMock,
    mock_cleanup: MagicMock,
) -> None:
    deps = _make_deps(dry_run=True)
    issue = _make_issue()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Fix login bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = [issue]
    deps.github_client.get_linked_branch.return_value = "fix/1-fix-login-bug"
    deps.github_client.get_open_pr_url.return_value = None
    mock_clone.return_value = MagicMock()
    mock_sprint.return_value = (["app.py"], "summary")

    results = run_for_repo(_make_repo_config(), deps)

    success = next(r for r in results if r.status == "success")
    assert success.pr_url is None
    assert success.written_files == ["app.py"]
    deps.github_client.open_pr.assert_not_called()
    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# run_for_repo — noop when sprint writes nothing
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.run_sprint")
@patch("agent.application.run_repo.build_file_tree", return_value="")
@patch("agent.application.run_repo.extract_keywords", return_value=[])
@patch("agent.application.run_repo.select_relevant_files", return_value=[])
@patch("agent.application.run_repo.score_issues")
def test_noop_when_no_files_written(
    mock_score_issues: MagicMock,
    mock_select_rel: MagicMock,
    mock_keywords: MagicMock,
    mock_tree: MagicMock,
    mock_sprint: MagicMock,
    mock_clone: MagicMock,
    mock_cleanup: MagicMock,
) -> None:
    deps = _make_deps()
    issue = _make_issue()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Fix login bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = [issue]
    deps.github_client.get_linked_branch.return_value = "fix/1-fix-login-bug"
    deps.github_client.get_open_pr_url.return_value = None
    mock_clone.return_value = MagicMock()
    mock_sprint.return_value = ([], "")

    results = run_for_repo(_make_repo_config(), deps)

    noop = next(r for r in results if r.status == "noop")
    assert noop.written_files == []
    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# run_for_repo — cleanup called even on error
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.score_issues")
def test_cleanup_called_on_error(
    mock_score_issues: MagicMock,
    mock_clone: MagicMock,
    mock_cleanup: MagicMock,
) -> None:
    deps = _make_deps()
    issue = _make_issue()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Fix login bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = [issue]
    deps.github_client.get_linked_branch.return_value = "fix/1-fix-login-bug"
    deps.github_client.get_open_pr_url.return_value = None
    mock_clone.side_effect = RuntimeError("network failure")

    results = run_for_repo(_make_repo_config(), deps)

    error = next(r for r in results if r.status == "error")
    assert "network failure" in (error.error_message or "")
    mock_cleanup.assert_not_called()  # clone failed → repo is None → shutil.rmtree used instead


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.run_sprint")
@patch("agent.application.run_repo.build_file_tree", return_value="")
@patch("agent.application.run_repo.extract_keywords", return_value=[])
@patch("agent.application.run_repo.select_relevant_files", return_value=[])
@patch("agent.application.run_repo.score_issues")
def test_cleanup_called_on_sprint_error(
    mock_score_issues: MagicMock,
    mock_select_rel: MagicMock,
    mock_keywords: MagicMock,
    mock_tree: MagicMock,
    mock_sprint: MagicMock,
    mock_clone: MagicMock,
    mock_cleanup: MagicMock,
) -> None:
    deps = _make_deps()
    issue = _make_issue()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Fix login bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = [issue]
    deps.github_client.get_linked_branch.return_value = "fix/1-fix-login-bug"
    deps.github_client.get_open_pr_url.return_value = None
    mock_clone.return_value = MagicMock()
    mock_sprint.side_effect = RuntimeError("LLM exploded")

    results = run_for_repo(_make_repo_config(), deps)

    error = next(r for r in results if r.status == "error")
    assert error.status == "error"
    mock_cleanup.assert_called_once()
