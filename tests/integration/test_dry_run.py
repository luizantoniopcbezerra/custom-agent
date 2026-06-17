"""Integration tests for NightlyCodeAgent.

These tests run against real GitHub and OpenRouter APIs.
They are skipped by default and require:
  - GH_TOKEN env var (PAT with `repo` scope)
  - OPENROUTER_API_KEY env var
  - TEST_REPO_OWNER and TEST_REPO_NAME env vars pointing to a repo with open issues

Run with:
    pytest tests/integration/ -m integration -v

Or set RUN_INTEGRATION=true to run automatically in CI.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_GH_TOKEN = os.environ.get("GH_TOKEN", "")
_OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
_TEST_REPO_OWNER = os.environ.get("TEST_REPO_OWNER", "")
_TEST_REPO_NAME = os.environ.get("TEST_REPO_NAME", "")

_SECRETS_AVAILABLE = bool(_GH_TOKEN and _OPENROUTER_KEY and _TEST_REPO_OWNER and _TEST_REPO_NAME)
_SKIP_REASON = (
    "Integration tests require GH_TOKEN, OPENROUTER_API_KEY, "
    "TEST_REPO_OWNER, and TEST_REPO_NAME env vars."
)


@pytest.mark.timeout(120)
@pytest.mark.skipif(not _SECRETS_AVAILABLE, reason=_SKIP_REASON)
def test_dry_run_no_pr_created() -> None:
    """Pipeline runs end-to-end in dry_run mode: no branch created, no PR opened."""
    from agent.application.run_repo import RunRepoDeps, run_for_repo
    from agent.config import AgentConfig, AgentSettings, OpenRouterConfig
    from agent.domain.models import RepoConfig
    from agent.infrastructure.github_client import GithubClient
    from agent.infrastructure.llm_client import LLMClient
    from agent.infrastructure.rate_limiter import RateLimiter

    config = AgentConfig.model_construct(
        openrouter_api_key=_OPENROUTER_KEY,
        gh_token=_GH_TOKEN,
        dry_run=True,
        openrouter=OpenRouterConfig(),
        agent=AgentSettings(),
        repos=[],
    )
    rate_limiter = RateLimiter(
        rpm=config.openrouter.max_requests_per_minute,
        rpd=config.openrouter.max_requests_per_day,
    )
    llm_client = LLMClient(
        model=config.openrouter.model,
        base_url="https://openrouter.ai/api/v1",
        api_key=_OPENROUTER_KEY,
        rate_limiter=rate_limiter,
    )
    github_client = GithubClient(token=_GH_TOKEN)
    deps = RunRepoDeps(
        github_client=github_client,
        llm_client=llm_client,
        config=config,
    )
    repo_config = RepoConfig(owner=_TEST_REPO_OWNER, name=_TEST_REPO_NAME)

    result = run_for_repo(repo_config, deps)

    assert result.status in ("success", "noop"), (
        f"Expected status 'success' or 'noop', got '{result.status}': {result.error_message}"
    )
    # In dry_run mode, no PR should ever be opened
    assert result.pr_url is None, f"pr_url should be None in dry_run, got: {result.pr_url}"

    # Verify no branch was created on the remote
    if result.status == "success" and result.branch_name:
        gh_repo = github_client.get_repo(repo_config)
        branches = [b.name for b in gh_repo.get_branches()]
        assert result.branch_name not in branches, (
            f"Branch '{result.branch_name}' was created on remote despite dry_run=True"
        )


@pytest.mark.timeout(120)
@pytest.mark.skipif(not _SECRETS_AVAILABLE, reason=_SKIP_REASON)
@pytest.mark.skipif(
    not os.environ.get("RUN_IDEMPOTENCY_TEST"),
    reason="Idempotency test creates real PRs — set RUN_IDEMPOTENCY_TEST=true to enable.",
)
def test_idempotency() -> None:
    """Running the pipeline twice for the same repo returns noop on the second run.

    This test creates a real PR on the test repo. The PR is deleted in teardown.
    Requires RUN_IDEMPOTENCY_TEST=true in addition to the standard secrets.
    """
    from github import Github
    from github.Auth import Token

    from agent.application.run_repo import RunRepoDeps, run_for_repo
    from agent.config import AgentConfig, AgentSettings, OpenRouterConfig
    from agent.domain.models import RepoConfig
    from agent.infrastructure.github_client import GithubClient
    from agent.infrastructure.llm_client import LLMClient
    from agent.infrastructure.rate_limiter import RateLimiter

    config = AgentConfig.model_construct(
        openrouter_api_key=_OPENROUTER_KEY,
        gh_token=_GH_TOKEN,
        dry_run=False,
        openrouter=OpenRouterConfig(),
        agent=AgentSettings(),
        repos=[],
    )
    rate_limiter = RateLimiter(
        rpm=config.openrouter.max_requests_per_minute,
        rpd=config.openrouter.max_requests_per_day,
    )
    llm_client = LLMClient(
        model=config.openrouter.model,
        base_url="https://openrouter.ai/api/v1",
        api_key=_OPENROUTER_KEY,
        rate_limiter=rate_limiter,
    )
    github_client = GithubClient(token=_GH_TOKEN)
    deps = RunRepoDeps(
        github_client=github_client,
        llm_client=llm_client,
        config=config,
    )
    repo_config = RepoConfig(owner=_TEST_REPO_OWNER, name=_TEST_REPO_NAME)
    gh = Github(auth=Token(_GH_TOKEN))
    gh_repo = gh.get_repo(f"{_TEST_REPO_OWNER}/{_TEST_REPO_NAME}")
    pr_to_close: list[int] = []

    try:
        first = run_for_repo(repo_config, deps)
        if first.status == "success" and first.pr_url:
            pr_number = int(first.pr_url.rsplit("/", 1)[-1])
            pr_to_close.append(pr_number)

        second = run_for_repo(repo_config, deps)
        assert second.status == "noop", (
            f"Expected 'noop' on second run, got '{second.status}': {second.error_message}"
        )
    finally:
        for pr_num in pr_to_close:
            try:
                pr = gh_repo.get_pull(pr_num)
                pr.edit(state="closed")
            except Exception:
                pass
