from __future__ import annotations

import re

from agent.domain.models import IssueCandidate

_CONVENTIONAL_RE = re.compile(r"^([a-zA-Z]+):\s+.+")


def filter_conventional(
    issues: list[dict[str, object]],
    conventional_types: list[str],
) -> list[dict[str, object]]:
    """Keep only issues matching 'type: description'. If conventional_types is empty, skip filter."""
    if not conventional_types:
        return issues
    allowed = {t.lower() for t in conventional_types}
    result = []
    for issue in issues:
        m = _CONVENTIONAL_RE.match(str(issue.get("title", "")).strip())
        if m and m.group(1).lower() in allowed:
            result.append(issue)
    return result


_EASY_KEYWORDS = frozenset(
    [
        "typo",
        "docs",
        "documentation",
        "simple",
        "rename",
        "fix typo",
        "readme",
        "comment",
        "spelling",
    ]
)


def _heuristic_score(issue_data: dict[str, object]) -> int:
    title = str(issue_data.get("title", "")).lower()
    body = str(issue_data.get("body", "")).lower()
    combined = title + " " + body
    if any(kw in combined for kw in _EASY_KEYWORDS):
        return 2
    if len(body) < 100:
        return 2
    return 7


def score_issues(issues: list[dict[str, object]]) -> list[IssueCandidate]:
    if not issues:
        return []

    candidates: list[IssueCandidate] = []
    for issue in issues:
        number = int(str(issue["number"]))
        score = _heuristic_score(issue)
        candidates.append(
            IssueCandidate(
                number=number,
                title=str(issue["title"]),
                body=str(issue.get("body", "") or ""),
                score=max(1, min(10, score)),
                reason="heuristic",
                repo_full_name=str(issue["repo_full_name"]),
                created_at=str(issue["created_at"]),
            )
        )

    return candidates


def select_best(candidates: list[IssueCandidate]) -> IssueCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c.score, c.created_at))
