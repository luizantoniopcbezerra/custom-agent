from agent.domain.issue_selector import _heuristic_score, score_issues, select_best
from agent.domain.models import IssueCandidate


def _make_issue(
    number: int, title: str, body: str, created_at: str = "2026-01-01T00:00:00"
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "repo_full_name": "alice/repo",
        "created_at": created_at,
    }


def test_score_issues_returns_all_issues() -> None:
    issues = [
        _make_issue(1, "Fix typo", "Small fix"),
        _make_issue(2, "Refactor auth", "x" * 300),
    ]

    result = score_issues(issues)

    assert len(result) == 2
    assert {c.number for c in result} == {1, 2}


def test_score_issues_uses_heuristic() -> None:
    issues = [
        _make_issue(1, "Fix typo in readme", ""),
        _make_issue(2, "Refactor", "x" * 300),
    ]

    result = score_issues(issues)

    numbers = {c.number: c.score for c in result}
    assert numbers[1] == 2   # typo keyword → easy
    assert numbers[2] == 7   # long body, no keywords → hard


def test_score_issues_empty_list() -> None:
    result = score_issues([])
    assert result == []


def test_score_issues_reason_is_heuristic() -> None:
    issues = [_make_issue(1, "Fix login", "x")]
    result = score_issues(issues)
    assert result[0].reason == "heuristic"


def test_select_best_returns_lowest_score() -> None:
    candidates = [
        IssueCandidate(
            number=1, title="A", body="", score=5, reason="",
            repo_full_name="a/b", created_at="2026-01-01",
        ),
        IssueCandidate(
            number=2, title="B", body="", score=2, reason="",
            repo_full_name="a/b", created_at="2026-01-02",
        ),
    ]
    best = select_best(candidates)
    assert best is not None
    assert best.number == 2


def test_select_best_tie_broken_by_oldest() -> None:
    candidates = [
        IssueCandidate(
            number=1, title="A", body="", score=3, reason="",
            repo_full_name="a/b", created_at="2026-01-05",
        ),
        IssueCandidate(
            number=2, title="B", body="", score=3, reason="",
            repo_full_name="a/b", created_at="2026-01-01",
        ),
    ]
    best = select_best(candidates)
    assert best is not None
    assert best.number == 2


def test_select_best_returns_none_for_empty() -> None:
    assert select_best([]) is None


def test_heuristic_score_easy_keyword() -> None:
    issue = {"title": "Fix typo in README", "body": ""}
    assert _heuristic_score(issue) == 2


def test_heuristic_score_short_body() -> None:
    issue = {"title": "Something vague", "body": "short"}
    assert _heuristic_score(issue) == 2


def test_heuristic_score_hard() -> None:
    issue = {"title": "Refactor entire auth module", "body": "x" * 300}
    assert _heuristic_score(issue) == 7


def test_all_issues_returned_regardless_of_score() -> None:
    """score_issues no longer filters — all issues come back regardless of difficulty."""
    issues = [
        _make_issue(1, "Big refactor", "x" * 300),
        _make_issue(2, "Complex migration", "x" * 300),
    ]

    candidates = score_issues(issues)
    assert len(candidates) == 2
