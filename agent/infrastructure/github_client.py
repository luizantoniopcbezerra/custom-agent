import requests as http_requests
from github import Auth, Github
from github.PullRequest import PullRequest
from github.Repository import Repository
from rich.console import Console

from agent.domain.models import RepoConfig

console = Console()

PR_BODY_TEMPLATE = """\
## Summary

Automated fix for issue #{issue_number}: {issue_title}

## Changes

{summary}

## Sprint Docs

Study, context, plan and self-review are available at:
`docs/Sprints/{sprint_slug}/`

Closes #{issue_number}

---
*This PR was opened automatically by [Nightcrawler Agent](https://github.com).*
"""

_MAX_ISSUES = 20
_MAX_REPOS = 50


class GithubClient:
    """Thin wrapper around PyGithub exposing only the operations the agent needs."""

    def __init__(self, token: str) -> None:
        self._gh = Github(auth=Auth.Token(token))
        self._token = token
        try:
            self.login = self._gh.get_user().login
            if not self.login:
                raise ValueError("Empty login returned")
        except Exception as exc:
            raise ValueError(
                f"GitHub authentication failed. Check that GH_TOKEN is valid. ({exc})"
            ) from exc

    def get_repos_with_assigned_issues(self) -> list[RepoConfig]:
        """Return RepoConfig for every repo where the authenticated user has open assigned issues."""
        issues = self._gh.get_user().get_issues(filter="assigned", state="open")
        seen: set[str] = set()
        repos: list[RepoConfig] = []
        for issue in issues:
            if len(repos) >= _MAX_REPOS:
                break
            if issue.pull_request is not None:
                continue
            full_name = issue.repository.full_name
            if full_name in seen:
                continue
            seen.add(full_name)
            owner, name = full_name.split("/", 1)
            repos.append(
                RepoConfig(owner=owner, name=name, branch=issue.repository.default_branch)
            )
        return repos

    def get_repos_from_notifications(self) -> list[RepoConfig]:
        """Return repos that have unread issue/PR notifications — supplements assigned discovery."""
        seen: set[str] = set()
        repos: list[RepoConfig] = []
        try:
            for notif in self._gh.get_user().get_notifications():
                if len(repos) >= _MAX_REPOS:
                    break
                if notif.subject.type not in ("Issue", "PullRequest"):
                    continue
                full_name = notif.repository.full_name
                if full_name in seen:
                    continue
                seen.add(full_name)
                owner, name = full_name.split("/", 1)
                repos.append(
                    RepoConfig(owner=owner, name=name, branch=notif.repository.default_branch)
                )
        except Exception as exc:
            console.print(f"[GitHub] Could not fetch notifications: {exc}")
        return repos

    def get_repo(self, repo_config: RepoConfig) -> Repository:
        return self._gh.get_repo(repo_config.full_name)

    def get_open_issues(self, repo_config: RepoConfig) -> list[dict[str, object]]:
        """Return up to 20 open issues as plain dicts, applying label filters."""
        repo = self.get_repo(repo_config)
        label_objects = (
            [repo.get_label(lbl) for lbl in repo_config.labels] if repo_config.labels else []
        )
        raw_issues = repo.get_issues(state="open", labels=label_objects)

        results: list[dict[str, object]] = []
        for issue in raw_issues:
            if len(results) >= _MAX_ISSUES:
                break
            issue_labels = {lbl.name for lbl in issue.labels}
            if issue_labels & set(repo_config.exclude_labels):
                continue
            # Skip pull requests (GitHub API returns PRs in get_issues)
            if issue.pull_request is not None:
                continue
            results.append(
                {
                    "number": issue.number,
                    "title": issue.title,
                    "body": issue.body or "",
                    "labels": [lbl.name for lbl in issue.labels],
                    "created_at": issue.created_at.isoformat(),
                    "repo_full_name": repo_config.full_name,
                }
            )
        return results

    def get_linked_branch(self, owner: str, repo_name: str, issue_number: int) -> str | None:
        """Return the branch linked to an issue. Tries GraphQL first, then branch name fallback."""
        # Primary: GitHub GraphQL linkedBranches (requires token with repo scope)
        query = """query($owner:String!,$repo:String!,$number:Int!){
          repository(owner:$owner,name:$repo){
            issue(number:$number){linkedBranches(first:10){nodes{ref{name}}}}
          }
        }"""
        try:
            resp = http_requests.post(
                "https://api.github.com/graphql",
                json={"query": query, "variables": {"owner": owner, "repo": repo_name, "number": issue_number}},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10,
            )
            payload = resp.json()
            if "errors" in payload:
                console.print(f"[GitHub] GraphQL errors for issue #{issue_number}: {payload['errors']}")
            data = payload.get("data") or {}
            nodes = (
                ((data.get("repository") or {})
                 .get("issue") or {})
                .get("linkedBranches", {})
                .get("nodes", [])
            )
            for node in nodes:
                name = node.get("ref", {}).get("name")
                if name:
                    console.print(f"[GitHub] Linked branch via GraphQL: {name}")
                    return name
        except Exception as exc:
            console.print(f"[GitHub] GraphQL request failed: {exc}")

        # Fallback: branch whose name starts with "{issue_number}-"
        prefix = f"{issue_number}-"
        try:
            repo = self._gh.get_repo(f"{owner}/{repo_name}")
            for branch in repo.get_branches():
                if branch.name.startswith(prefix):
                    console.print(f"[GitHub] Linked branch via name fallback: {branch.name}")
                    return branch.name
        except Exception as exc:
            console.print(f"[GitHub] Branch fallback failed: {exc}")

        return None

    def get_open_pr_url(self, repo: Repository, issue_number: int) -> str | None:
        """Return the URL of an open PR that closes this issue, or None."""
        query = f"repo:{repo.full_name} is:pr is:open closes #{issue_number} in:body"
        results = self._gh.search_issues(query)
        for pr in results:
            return pr.html_url
        return None

    def open_pr(
        self,
        repo: Repository,
        branch_name: str,
        issue_number: int,
        issue_title: str,
        summary: str,
        sprint_slug: str = "",
    ) -> PullRequest:
        body = PR_BODY_TEMPLATE.format(
            issue_number=issue_number,
            issue_title=issue_title,
            summary=summary,
            sprint_slug=sprint_slug,
        )
        pr = repo.create_pull(
            title=f"fix: {issue_title}",
            body=body,
            head=branch_name,
            base=repo.default_branch,
        )
        console.print(f"[GitHub] PR opened: {pr.html_url}")
        return pr
