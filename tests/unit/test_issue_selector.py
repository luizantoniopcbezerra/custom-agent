import json
from unittest.mock import MagicMock

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


def _make_llm_client(response_content: str) -> MagicMock:
    client = MagicMock()
    msg = MagicMock()
    msg.content = response_content
    client.chat.return_value.choices = [MagicMock(message=msg)]
    return client


def test_score_issues_with_valid_llm_json() -> None:
    issues = [
        _make_issue(1, "Fix typo", "Small fix"),
        _make_issue(2, "Refactor auth", "x" * 300),
    ]
    llm_response = json.dumps(
        [
            {"number": 1, "score": 2, "reason": "trivial"},
            {"number": 2, "score": 8, "reason": "complex"},
        ]
    )
    client = _make_llm_client(llm_response)

    result = score_issues(issues, client, threshold=5)

    assert len(result) == 1
    assert result[0].number == 1
    assert result[0].score == 2
    assert result[0].reason == "trivial"
    client.chat.assert_called_once()


def test_score_issues_fallback_on_invalid_json() -> None:
    issues = [
        _make_issue(1, "Fix typo in readme", ""),
        _make_issue(2, "Refactor", "x" * 300),
    ]
    client = _make_llm_client("not valid json at all")

    result = score_issues(issues, client, threshold=5)

    # issue 1 has "typo" keyword → score 2 (passes threshold 5)
    # issue 2 has long body, no keywords → score 7 (filtered out)
    assert len(result) == 1
    assert result[0].number == 1
    assert result[0].reason == "heuristic fallback"


def test_score_issues_filters_by_threshold() -> None:
    issues = [_make_issue(1, "Big refactor", "x" * 300)]
    llm_response = json.dumps([{"number": 1, "score": 9, "reason": "hard"}])
    client = _make_llm_client(llm_response)

    result = score_issues(issues, client, threshold=5)

    assert result == []


def test_score_issues_empty_list_makes_no_llm_call() -> None:
    client = MagicMock()

    result = score_issues([], client, threshold=5)

    assert result == []
    client.chat.assert_not_called()


def test_select_best_returns_lowest_score() -> None:
    candidates = [
        IssueCandidate(
            number=1,
            title="A",
            body="",
            score=5,
            reason="",
            repo_full_name="a/b",
            created_at="2026-01-01",
        ),
        IssueCandidate(
            number=2,
            title="B",
            body="",
            score=2,
            reason="",
            repo_full_name="a/b",
            created_at="2026-01-02",
        ),
    ]
    best = select_best(candidates)
    assert best is not None
    assert best.number == 2


def test_select_best_tie_broken_by_oldest() -> None:
    candidates = [
        IssueCandidate(
            number=1,
            title="A",
            body="",
            score=3,
            reason="",
            repo_full_name="a/b",
            created_at="2026-01-05",
        ),
        IssueCandidate(
            number=2,
            title="B",
            body="",
            score=3,
            reason="",
            repo_full_name="a/b",
            created_at="2026-01-01",
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


def test_score_issues_ignores_unknown_numbers_in_llm_response() -> None:
    """LLM returns a score for issue 999 which isn't in the input list — must be ignored."""
    issues = [_make_issue(1, "Fix login", "x")]
    llm_response = json.dumps(
        [
            {"number": 1, "score": 2, "reason": "easy"},
            {"number": 999, "score": 3, "reason": "unknown"},
        ]
    )
    client = _make_llm_client(llm_response)

    result = score_issues(issues, client, threshold=5)

    assert len(result) == 1
    assert result[0].number == 1
    assert result[0].score == 2


def test_all_issues_above_threshold_pipeline_returns_none() -> None:
    """When all issues score above threshold, score_issues is empty and select_best is None."""
    issues = [
        _make_issue(1, "Big refactor", "x" * 300),
        _make_issue(2, "Complex migration", "x" * 300),
    ]
    llm_response = json.dumps(
        [
            {"number": 1, "score": 8, "reason": "hard"},
            {"number": 2, "score": 9, "reason": "very hard"},
        ]
    )
    client = _make_llm_client(llm_response)

    candidates = score_issues(issues, client, threshold=5)
    assert candidates == []
    assert select_best(candidates) is None
