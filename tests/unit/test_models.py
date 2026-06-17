import pytest
from pydantic import ValidationError

from agent.domain.models import AgentRun, IssueCandidate, RepoConfig


def _make_issue(**overrides: object) -> IssueCandidate:
    defaults = {
        "number": 1,
        "title": "Fix typo in README",
        "body": "There is a typo on line 5.",
        "score": 2,
        "reason": "trivial text change",
        "repo_full_name": "user/repo",
        "created_at": "2026-06-01T00:00:00Z",
    }
    return IssueCandidate(**{**defaults, **overrides})


def test_issue_candidate_valid() -> None:
    issue = _make_issue()
    assert issue.number == 1
    assert issue.score == 2
    assert issue.repo_full_name == "user/repo"


def test_issue_candidate_score_below_minimum() -> None:
    with pytest.raises(ValidationError):
        _make_issue(score=0)


def test_issue_candidate_score_above_maximum() -> None:
    with pytest.raises(ValidationError):
        _make_issue(score=11)


def test_issue_candidate_frozen() -> None:
    issue = _make_issue()
    with pytest.raises(ValidationError):
        issue.score = 5  # type: ignore[misc]


def test_repo_config_full_name() -> None:
    repo = RepoConfig(owner="alice", name="my-project")
    assert repo.full_name == "alice/my-project"


def test_repo_config_defaults() -> None:
    repo = RepoConfig(owner="alice", name="my-project")
    assert repo.branch == "main"
    assert repo.labels == []
    assert repo.exclude_labels == []
    assert repo.max_issues_per_run == 1


def test_repo_config_max_issues_minimum() -> None:
    with pytest.raises(ValidationError):
        RepoConfig(owner="alice", name="repo", max_issues_per_run=0)


def test_agent_run_valid_status() -> None:
    run = AgentRun(
        issue=None,
        written_files=[],
        branch_name="agent/issue-1-fix",
        pr_url=None,
        status="noop",
    )
    assert run.status == "noop"
    assert run.error_message is None


def test_agent_run_invalid_status() -> None:
    with pytest.raises(ValidationError):
        AgentRun(
            issue=None,
            written_files=[],
            branch_name="agent/issue-1-fix",
            pr_url=None,
            status="unknown",  # type: ignore[arg-type]
        )
