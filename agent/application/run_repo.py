from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass

from git import Repo
from rich.console import Console

from agent.config import AgentConfig
from agent.domain.context_builder import build_file_tree, extract_keywords, select_relevant_files
from agent.domain.issue_selector import filter_conventional, score_issues, select_best
from agent.domain.models import AgentRun, IssueCandidate, RepoConfig
from agent.domain.sprint_pipeline import run_sprint
from agent.infrastructure import git_ops
from agent.infrastructure.email_client import EmailClient
from agent.infrastructure.github_client import GithubClient
from agent.infrastructure.llm_client import LLMClient
from agent.infrastructure.model_router import route_model

console = Console()


@dataclass
class RunRepoDeps:
    github_client: GithubClient
    llm_client: LLMClient
    config: AgentConfig
    email_client: EmailClient | None = None
    gh_token: str = ""  # per-account override for git clone; falls back to config.gh_token

    def token(self) -> str:
        return self.gh_token or self.config.gh_token


def _slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:50]


def _get_candidates(
    repo_config: RepoConfig, deps: RunRepoDeps
) -> tuple[list[tuple[IssueCandidate, str]], list[AgentRun]]:
    """Score and filter issues. Returns (actionable_candidates, pending_pr_runs)."""
    issues = deps.github_client.get_open_issues(repo_config)
    if not issues:
        console.print(f"[{repo_config.full_name}] No open issues found.")
        return [], []

    conventional_types = deps.config.agent.conventional_types
    if conventional_types:
        issues = filter_conventional(issues, conventional_types)
        if not issues:
            console.print(
                f"[{repo_config.full_name}] No issues match conventional types {conventional_types}."
            )
            return [], []

    scored = score_issues(issues)
    if not scored:
        return [], []

    # Sort ascending by score so we try easiest first
    scored.sort(key=lambda c: (c.score, c.created_at))

    actionable: list[tuple[IssueCandidate, str]] = []
    pending_prs: list[AgentRun] = []

    gh_repo = deps.github_client.get_repo(repo_config)

    for issue in scored:
        linked_branch = deps.github_client.get_linked_branch(
            repo_config.owner, repo_config.name, issue.number
        )
        if linked_branch is None:
            console.print(
                f"[{repo_config.full_name}] Issue #{issue.number} '{issue.title}'"
                " has no linked branch — skipping."
            )
            continue

        existing_pr_url = deps.github_client.get_open_pr_url(gh_repo, issue.number)
        if existing_pr_url:
            console.print(
                f"[{repo_config.full_name}] Issue #{issue.number} already has PR"
                f" {existing_pr_url} — reporting as pending."
            )
            pending_prs.append(
                AgentRun(
                    issue=issue,
                    written_files=[],
                    branch_name=linked_branch,
                    pr_url=existing_pr_url,
                    status="pending_pr",
                )
            )
            continue

        actionable.append((issue, linked_branch))

    return actionable, pending_prs


def _attempt_issue(
    issue: IssueCandidate,
    branch_name: str,
    repo_config: RepoConfig,
    deps: RunRepoDeps,
) -> AgentRun:
    """Clone, run sprint pipeline, commit and push for a single issue."""
    sprint_slug = f"{issue.number}-{_slugify(issue.title)}"
    tmp_dir = tempfile.mkdtemp(prefix="nightcrawler-")
    repo: Repo | None = None

    try:
        repo = git_ops.clone(repo_config.owner, repo_config.name, deps.token(), tmp_dir)

        file_tree = build_file_tree(tmp_dir)
        keywords = extract_keywords(issue.title, issue.body)
        relevant_files = select_relevant_files(
            tmp_dir,
            keywords,
            max_files=deps.config.agent.max_context_files,
            max_bytes=deps.config.agent.max_file_size_bytes,
        )
        routed_model = route_model(issue.score)
        console.print(f"[Router] score={issue.score} → {routed_model}")

        written_files, junior_summary = run_sprint(
            issue=issue,
            file_tree=file_tree,
            relevant_files=relevant_files,
            llm_client=deps.llm_client,
            repo_root=tmp_dir,
            max_calls=deps.config.agent.max_tool_calls_per_issue,
            max_file_bytes=deps.config.agent.max_file_size_bytes,
            model=routed_model,
            sprint_slug=sprint_slug,
        )

        if not written_files:
            console.print(f"[{repo_config.full_name}] No files written — noop.")
            return AgentRun(
                issue=issue,
                written_files=[],
                branch_name=branch_name,
                pr_url=None,
                status="noop",
                skip_reason="agent wrote no files",
            )

        if deps.config.dry_run:
            console.print(f"[{repo_config.full_name}] dry_run=True — skipping commit/push.")
            return AgentRun(
                issue=issue,
                written_files=written_files,
                branch_name=branch_name,
                pr_url=None,
                status="success",
            )

        commit_msg = f"fix: {issue.title} (closes #{issue.number})"
        git_ops.commit_and_push(repo, branch_name, commit_msg, create=False)

        gh_repo = deps.github_client.get_repo(repo_config)
        summary = (
            f"Automated fix for issue #{issue.number}. "
            f"Modified files: {', '.join(written_files)}"
        )
        pr = deps.github_client.open_pr(
            repo=gh_repo,
            branch_name=branch_name,
            issue_number=issue.number,
            issue_title=issue.title,
            summary=summary,
            sprint_slug=sprint_slug,
        )
        console.print(f"[{repo_config.full_name}] PR opened: {pr.html_url}")

        if deps.email_client is not None:
            deps.email_client.send(
                subject=f"[NIGHTCRAWLER] PR Aberto - {issue.title}",
                body=(
                    f"Repositório: {repo_config.full_name}\n"
                    f"Issue: #{issue.number} - {issue.title}\n"
                    f"PR: {pr.html_url}\n"
                    f"\n---\n\n"
                    f"{junior_summary}"
                ),
            )

        return AgentRun(
            issue=issue,
            written_files=written_files,
            branch_name=branch_name,
            pr_url=pr.html_url,
            status="success",
            junior_summary=junior_summary,
        )

    except Exception as exc:
        console.print(f"[{repo_config.full_name}] ERROR on issue #{issue.number}: {exc}")
        return AgentRun(
            issue=issue,
            written_files=[],
            branch_name=branch_name,
            pr_url=None,
            status="error",
            error_message=str(exc),
        )

    finally:
        if repo is not None:
            git_ops.cleanup(repo, tmp_dir)
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def run_for_repo(repo_config: RepoConfig, deps: RunRepoDeps) -> list[AgentRun]:
    """Process a repo. Returns one AgentRun per issue attempted plus pending PRs."""
    console.print(f"\n[bold]Processing {repo_config.full_name}...[/bold]")
    actionable, pending_prs = _get_candidates(repo_config, deps)

    if not actionable and not pending_prs:
        return [AgentRun(
            issue=None,
            written_files=[],
            branch_name="",
            pr_url=None,
            status="noop",
            skip_reason="no actionable issues found",
        )]

    results: list[AgentRun] = list(pending_prs)

    for issue, branch in actionable:
        console.print(
            f"[{repo_config.full_name}] Attempting issue #{issue.number}"
            f" (score={issue.score}, branch={branch}): {issue.title}"
        )
        result = _attempt_issue(issue, branch, repo_config, deps)
        results.append(result)

        if result.status == "success":
            break  # one success per repo per run is enough

    return results
