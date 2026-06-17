from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from pydantic import ValidationError
from rich.console import Console

from agent.application.run_repo import RunRepoDeps, run_for_repo
from agent.config import AgentConfig
from agent.domain.models import AgentRun, RepoConfig
from agent.infrastructure.email_client import EmailClient
from agent.infrastructure.github_client import GithubClient
from agent.infrastructure.llm_client import LLMClient
from agent.infrastructure.rate_limiter import RateLimiter

console = Console()

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _build_accounts(config: AgentConfig) -> list[tuple[str, GithubClient]]:
    """Return (token, GithubClient) pairs for every configured account."""
    if config.accounts:
        pairs: list[tuple[str, GithubClient]] = []
        for account in config.accounts:
            token = os.environ.get(account.token_env, "")
            if not token:
                console.print(
                    f"[yellow]Skipping account: env var '{account.token_env}' is not set.[/yellow]"
                )
                continue
            try:
                gh = GithubClient(token=token)
                console.print(f"[green]Account loaded: {gh.login} ({account.token_env})[/green]")
                pairs.append((token, gh))
            except ValueError as exc:
                console.print(f"[red]Account {account.token_env} auth failed: {exc}[/red]")
        return pairs

    # Fallback: single account from GH_TOKEN
    if config.gh_token:
        try:
            gh = GithubClient(token=config.gh_token)
            console.print(f"[green]Account loaded: {gh.login} (GH_TOKEN)[/green]")
            return [(config.gh_token, gh)]
        except ValueError as exc:
            console.print(f"[red]GH_TOKEN auth failed: {exc}[/red]")

    return []


def _discover_repos(gh: GithubClient) -> list[RepoConfig]:
    assigned = gh.get_repos_with_assigned_issues()
    notif = gh.get_repos_from_notifications()

    seen: set[str] = {r.full_name for r in assigned}
    repos: list[RepoConfig] = list(assigned)
    for r in notif:
        if r.full_name not in seen:
            repos.append(r)
            seen.add(r.full_name)

    console.print(
        f"[green]  Discovered {len(repos)} repo(s) "
        f"({len(assigned)} assigned, {len(notif)} from notifications)[/green]"
    )
    return repos


def main() -> None:
    load_dotenv()  # ensures token env vars like GH_TOKEN_PERSONAL land in os.environ
    try:
        config = AgentConfig.from_yaml("config.yml")
    except ValidationError as exc:
        console.print("[bold red]Configuration error:[/bold red]")
        for error in exc.errors():
            console.print(f"  • {' → '.join(str(loc) for loc in error['loc'])}: {error['msg']}")
        sys.exit(1)

    rate_limiter = RateLimiter(
        rpm=config.openrouter.max_requests_per_minute,
        rpd=config.openrouter.max_requests_per_day,
    )
    llm_client = LLMClient(
        model=config.openrouter.model,
        base_url=_OPENROUTER_BASE_URL,
        api_key=config.openrouter_api_key,
        rate_limiter=rate_limiter,
    )
    email_client: EmailClient | None = None
    if config.email_enabled:
        email_client = EmailClient(
            from_addr=config.email_from,
            app_password=config.email_app_password,
            to_addr=config.email_to,
        )
    else:
        console.print("[yellow]Email not configured — skipping notifications.[/yellow]")

    accounts = _build_accounts(config)
    if not accounts:
        console.print("[bold red]No valid GitHub accounts available. Exiting.[/bold red]")
        sys.exit(1)

    results: list[AgentRun] = []
    successes = 0
    limit = config.agent.max_resolutions_per_run

    for token, gh in accounts:
        if successes >= limit:
            console.print(
                f"[yellow]Resolution limit ({limit}) reached — skipping remaining accounts.[/yellow]"
            )
            break

        console.print(f"\n[bold cyan]── Account: {gh.login} ──[/bold cyan]")

        repos = config.repos or _discover_repos(gh)

        if not repos:
            console.print(f"[yellow]  No repos found for {gh.login}.[/yellow]")
            continue

        deps = RunRepoDeps(
            github_client=gh,
            llm_client=llm_client,
            config=config,
            email_client=email_client,
            gh_token=token,
        )

        for repo_config in repos:
            if successes >= limit:
                break
            repo_results = run_for_repo(repo_config, deps)
            results.extend(repo_results)
            successes += sum(1 for r in repo_results if r.status == "success")

    success = sum(1 for r in results if r.status == "success")
    noop = sum(1 for r in results if r.status == "noop")
    error = sum(1 for r in results if r.status == "error")
    pending = sum(1 for r in results if r.status == "pending_pr")

    console.print(
        f"\n[bold]Done.[/bold] Issues: {len(results)} | "
        f"success={success} noop={noop} error={error} pending_pr={pending}"
    )

    if email_client is not None:
        if success == 0 and error == 0 and noop == 0 and pending == 0:
            email_client.send(
                subject="[CUSTOM-AGENT] Relatório de Execução",
                body=(
                    "Olá!\n\n"
                    "O agente rodou esta noite mas não havia issues assignadas para mim "
                    "em nenhuma das contas configuradas.\n\n"
                    "Nenhuma ação foi necessária. Até amanhã!"
                ),
            )
        else:
            _send_summary(email_client, results)


def _send_summary(email_client: EmailClient, results: list[AgentRun]) -> None:
    opened = [r for r in results if r.status == "success" and r.pr_url]
    pending = [r for r in results if r.status == "pending_pr"]
    noops = [r for r in results if r.status == "noop"]
    errors = [r for r in results if r.status == "error"]

    lines: list[str] = [
        f"Issues processadas: {len(results)}",
        f"PRs abertos: {len(opened)}",
        f"PRs aguardando revisão: {len(pending)}",
        f"Sem ação: {len(noops)}",
        f"Erros: {len(errors)}",
        "",
    ]

    if opened:
        lines.append("✅ PRs abertos:")
        for r in opened:
            repo = r.issue.repo_full_name if r.issue else "?"
            title = r.issue.title if r.issue else "?"
            lines.append(f"  [{repo}] #{r.issue.number if r.issue else '?'} {title}")
            lines.append(f"    {r.pr_url}")
            if r.junior_summary:
                lines.append("")
                lines.append(r.junior_summary)
            lines.append("")
        lines.append("")

    if pending:
        lines.append("⏳ PRs aguardando sua revisão:")
        for r in pending:
            repo = r.issue.repo_full_name if r.issue else "?"
            title = r.issue.title if r.issue else "?"
            lines.append(f"  [{repo}] #{r.issue.number if r.issue else '?'} {title}")
            lines.append(f"    {r.pr_url}")
        lines.append("")

    if noops:
        lines.append("⏭ Sem ação (motivo):")
        for r in noops:
            repo = r.issue.repo_full_name if r.issue else "?"
            issue_ref = f"#{r.issue.number} {r.issue.title}" if r.issue else "nenhuma issue"
            reason = r.skip_reason or "nenhum arquivo escrito"
            lines.append(f"  [{repo}] {issue_ref} → {reason}")
        lines.append("")

    if errors:
        lines.append("❌ Erros:")
        for r in errors:
            repo = r.issue.repo_full_name if r.issue else "?"
            title = r.issue.title if r.issue else "?"
            lines.append(
                f"  [{repo}] #{r.issue.number if r.issue else '?'} {title}"
                f"\n    {r.error_message}"
            )
        lines.append("")

    email_client.send(
        subject="[CUSTOM-AGENT] Relatório de Execução",
        body="\n".join(lines),
    )


if __name__ == "__main__":
    main()
