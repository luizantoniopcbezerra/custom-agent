from __future__ import annotations

import json
import re

from agent.domain.models import IssueCandidate
from agent.infrastructure.llm_client import LLMClient

_CONVENTIONAL_RE = re.compile(r"^([a-zA-Z]+):\s+.+")

SCORE_PROMPT_TEMPLATE = """\
You are a triage assistant. Score each GitHub issue by implementation difficulty.

Score scale:
  1 = trivial (typo fix, rename, 1-line change)
  5 = moderate (small feature, medium bug)
  10 = very hard (large refactor, unclear spec, cross-cutting concern)

Issues to score:
{issues_json}

Return ONLY a JSON array — no markdown, no explanation, no code fences. Example:
[{{"number": 1, "score": 2, "reason": "Simple typo fix in docs"}}, {{"number": 2, "score": 7, "reason": "Requires refactoring multiple modules"}}]
"""

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


def score_issues(
    issues: list[dict[str, object]],
    llm_client: LLMClient,
    threshold: int,
) -> list[IssueCandidate]:
    if not issues:
        return []

    issues_json = json.dumps(
        [
            {
                "number": i["number"],
                "title": i["title"],
                "body": (str(i.get("body", "") or ""))[:500],
            }
            for i in issues
        ],
        ensure_ascii=False,
    )
    prompt = SCORE_PROMPT_TEMPLATE.format(issues_json=issues_json)
    response = llm_client.chat(messages=[{"role": "user", "content": prompt}])
    raw = response.choices[0].message.content or ""

    score_map: dict[int, tuple[int, str]] = {}
    try:
        parsed = json.loads(raw)
        for entry in parsed:
            num = int(entry["number"])
            score_map[num] = (int(entry["score"]), str(entry.get("reason", "")))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    candidates: list[IssueCandidate] = []
    for issue in issues:
        number = int(str(issue["number"]))
        if number in score_map:
            score, reason = score_map[number]
        else:
            score = _heuristic_score(issue)
            reason = "heuristic fallback"

        if score > threshold:
            continue

        candidates.append(
            IssueCandidate(
                number=number,
                title=str(issue["title"]),
                body=str(issue.get("body", "") or ""),
                score=max(1, min(10, score)),
                reason=reason,
                repo_full_name=str(issue["repo_full_name"]),
                created_at=str(issue["created_at"]),
            )
        )

    return candidates


def select_best(candidates: list[IssueCandidate]) -> IssueCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c.score, c.created_at))
