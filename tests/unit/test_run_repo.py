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
        reason="trivial",
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
# run_for_repo — noop paths
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.score_issues")
@patch("agent.application.run_repo.select_best")
def test_noop_when_no_issue_passes_threshold(
    mock_select_best: MagicMock,
    mock_score_issues: MagicMock,
) -> None:
    deps = _make_deps()
    deps.github_client.get_open_issues.return_value = [
        {
            "number": 1,
            "title": "Bug",
            "body": "x",
            "repo_full_name": "alice/repo",
            "created_at": "2026",
        }
    ]
    mock_score_issues.return_value = []
    mock_select_best.return_value = None

    result = run_for_repo(_make_repo_config(), deps)

    assert result.status == "noop"
    assert result.issue is None
    deps.github_client.get_repo.assert_not_called()


@patch("agent.application.run_repo.score_issues")
@patch("agent.application.run_repo.select_best")
def test_noop_when_pr_already_exists(
    mock_select_best: MagicMock,
    mock_score_issues: MagicMock,
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
    mock_select_best.return_value = issue
    deps.github_client.has_open_pr_for_issue.return_value = True

    result = run_for_repo(_make_repo_config(), deps)

    assert result.status == "noop"
    assert result.issue is None


# ---------------------------------------------------------------------------
# run_for_repo — success with dry_run
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.agentic_loop.run")
@patch("agent.application.run_repo.build_file_tree", return_value="app.py")
@patch("agent.application.run_repo.extract_keywords", return_value=["login"])
@patch("agent.application.run_repo.select_relevant_files", return_value=[])
@patch("agent.application.run_repo.score_issues")
@patch("agent.application.run_repo.select_best")
def test_success_dry_run_skips_commit(
    mock_select_best: MagicMock,
    mock_score_issues: MagicMock,
    mock_select_rel: MagicMock,
    mock_keywords: MagicMock,
    mock_tree: MagicMock,
    mock_loop: MagicMock,
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
    mock_select_best.return_value = issue
    deps.github_client.has_open_pr_for_issue.return_value = False
    mock_clone.return_value = MagicMock()
    mock_loop.return_value = ["app.py"]

    result = run_for_repo(_make_repo_config(), deps)

    assert result.status == "success"
    assert result.pr_url is None
    assert result.written_files == ["app.py"]
    deps.github_client.open_pr.assert_not_called()
    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# run_for_repo — noop when loop writes nothing
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.agentic_loop.run")
@patch("agent.application.run_repo.build_file_tree", return_value="")
@patch("agent.application.run_repo.extract_keywords", return_value=[])
@patch("agent.application.run_repo.select_relevant_files", return_value=[])
@patch("agent.application.run_repo.score_issues")
@patch("agent.application.run_repo.select_best")
def test_noop_when_no_files_written(
    mock_select_best: MagicMock,
    mock_score_issues: MagicMock,
    mock_select_rel: MagicMock,
    mock_keywords: MagicMock,
    mock_tree: MagicMock,
    mock_loop: MagicMock,
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
    mock_select_best.return_value = issue
    deps.github_client.has_open_pr_for_issue.return_value = False
    mock_clone.return_value = MagicMock()
    mock_loop.return_value = []  # loop wrote nothing

    result = run_for_repo(_make_repo_config(), deps)

    assert result.status == "noop"
    assert result.written_files == []
    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# run_for_repo — cleanup called even on error
# ---------------------------------------------------------------------------


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.score_issues")
@patch("agent.application.run_repo.select_best")
def test_cleanup_called_on_error(
    mock_select_best: MagicMock,
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
    mock_select_best.return_value = issue
    deps.github_client.has_open_pr_for_issue.return_value = False
    mock_clone.side_effect = RuntimeError("network failure")

    result = run_for_repo(_make_repo_config(), deps)

    assert result.status == "error"
    assert "network failure" in (result.error_message or "")
    # clone failed → repo is None → shutil.rmtree was called instead of cleanup
    mock_cleanup.assert_not_called()


@patch("agent.application.run_repo.git_ops.cleanup")
@patch("agent.application.run_repo.git_ops.clone")
@patch("agent.application.run_repo.agentic_loop.run")
@patch("agent.application.run_repo.build_file_tree", return_value="")
@patch("agent.application.run_repo.extract_keywords", return_value=[])
@patch("agent.application.run_repo.select_relevant_files", return_value=[])
@patch("agent.application.run_repo.score_issues")
@patch("agent.application.run_repo.select_best")
def test_cleanup_called_on_pipeline_error(
    mock_select_best: MagicMock,
    mock_score_issues: MagicMock,
    mock_select_rel: MagicMock,
    mock_keywords: MagicMock,
    mock_tree: MagicMock,
    mock_loop: MagicMock,
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
    mock_select_best.return_value = issue
    deps.github_client.has_open_pr_for_issue.return_value = False
    mock_clone.return_value = MagicMock()
    mock_loop.side_effect = RuntimeError("LLM exploded")

    result = run_for_repo(_make_repo_config(), deps)

    assert result.status == "error"
    mock_cleanup.assert_called_once()
