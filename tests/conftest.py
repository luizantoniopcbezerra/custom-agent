from __future__ import annotations

import os

import pytest

from agent.domain.models import IssueCandidate, RepoConfig


@pytest.fixture()
def sample_issue_candidate() -> IssueCandidate:
    return IssueCandidate(
        number=42,
        title="Fix login bug",
        body="Users cannot log in after password reset.",
        score=2,
        reason="small fix",
        repo_full_name="alice/repo",
        created_at="2026-01-15T10:00:00",
    )


@pytest.fixture()
def sample_repo_config() -> RepoConfig:
    return RepoConfig(
        owner="alice",
        name="repo",
        branch="main",
        labels=[],
        exclude_labels=["wontfix"],
    )


@pytest.fixture()
def tmp_repo(tmp_path: pytest.TempPathFactory) -> str:
    """Temporary directory with a minimal Python project structure (3 files)."""
    root = str(tmp_path)
    files = {
        "app.py": "def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n",
        "utils.py": "def helper(text: str) -> str:\n    return text.strip()\n",
        "README.md": "# My Project\n\nA simple Python project.\n",
    }
    for rel_path, content in files.items():
        abs_path = os.path.join(root, rel_path)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root
