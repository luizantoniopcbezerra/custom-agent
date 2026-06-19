from __future__ import annotations

from pathlib import Path
from typing import cast

from openai.types.chat import ChatCompletionMessageParam as MessageParam
from rich.console import Console

from agent.domain import agentic_loop
from agent.domain.models import IssueCandidate
from agent.infrastructure.llm_client import LLMClient

console = Console()

_PHASE_SYSTEM = """\
You are an autonomous software engineer preparing to implement a GitHub issue fix.
Be precise, technical, and concise. Produce only the requested markdown — no preamble, no apologies.
"""

_REVIEW_SYSTEM = """\
You are reviewing code changes produced by an autonomous agent.
Be critical and specific. Flag real problems only — no generic praise, no padding.
"""

_JUNIOR_SUMMARY_SYSTEM = """\
You are a senior developer writing an explanation for a junior developer.
Write in clear, friendly Portuguese (pt-BR). Use simple language — explain technical terms when you use them.
Be thorough but direct. The junior must be able to understand and maintain what was done.
"""

_JUNIOR_SUMMARY_PROMPT = """\
Escreva um relatório completo sobre o que foi feito nessa implementação, destinado a um desenvolvedor júnior.

## Issue resolvida
#{number}: {title}
{body}

## O que foi estudado
{study}

## O que foi planejado
{plan}

## O que foi implementado
Arquivos modificados: {written_files}
{files_with_content}

## Review realizado
{review}

---

Agora escreva o relatório em português, cobrindo obrigatoriamente:

1. **O problema** — o que estava errado ou faltando, em linguagem simples
2. **A solução escolhida** — por que essa abordagem e não outra
3. **O que cada arquivo alterado faz** — explique o papel de cada um no projeto
4. **O que foi mudado em cada arquivo e por quê** — linha por linha se necessário
5. **Como testar** — como o júnior pode verificar que a mudança funciona
6. **O que o júnior precisa saber para manter esse código** — armadilhas, convenções, dependências

Seja completo. Um júnior sem contexto deve entender tudo ao ler esse relatório.
"""

_STUDY_PROMPT = """\
Analyze this issue and the codebase snapshot below.

Issue #{number}: {title}
{body}

Repository structure:
```
{file_tree}
```

{relevant_files_section}

Produce a STUDY.md with exactly these sections:

## Root Cause
What exactly is broken or missing. Specific, no speculation.

## Relevant Files
Each file that matters, with one line explaining its role.

## Approach
The simplest correct solution. What changes and why this approach over alternatives.

## Out of Scope
What you will NOT touch and why.
"""

_CONTEXT_PROMPT = """\
Based on your study, document the project context.

Produce a CONTEXT.md with exactly these sections:

## Stack & Runtime
Languages, frameworks, key dependencies identified in the code.

## Conventions
Naming patterns, file structure, code style you observed and must follow.

## Architecture
How the relevant components fit together — brief, only what matters for this issue.

## Constraints
Existing patterns that must be preserved. Things that must not break.
"""

_PLAN_PROMPT = """\
Based on study and context, produce the implementation plan.

Produce a PLAN.md with exactly these sections:

## Tasks
Ordered list. Each item: `[file path] → [what changes] → [why]`.

## Out of Scope
Files and behaviors explicitly excluded.

## Risks
Assumptions that could break things if wrong.
"""

_REVIEW_PROMPT = """\
Review the implementation against sprint quality standards.

## Plan that was followed
{plan}

## Files written
{files_with_content}

Produce a REVIEW.md with exactly these sections:

## Object Calisthenics
Check each rule against the actual code written:
- One level of indentation per function
- No else after return
- Wrap primitives with meaning (where applicable)
- First-class collections (where applicable)
- Small functions and classes
- No abbreviations in names

## YAGNI / KISS / DRY
- Was only what was asked implemented?
- Is it the simplest correct solution?
- Is there any duplication?

## Correctness
Does the implementation fully resolve the issue as planned?

## Risks & Gaps
What could still break? What was not covered and why?
"""


def _chat_phase(
    messages: list[MessageParam],
    user_prompt: str,
    llm_client: LLMClient,
    model: str | None,
    label: str,
) -> str:
    """Append user prompt, call LLM, append response, return content."""
    messages.append({"role": "user", "content": user_prompt})
    console.print(f"[Sprint] Running {label}...")
    response = llm_client.chat(messages, model=model)
    if not response.choices:
        console.print(f"[Sprint] Empty/null choices from provider during {label} — returning empty.")
        return ""
    content = response.choices[0].message.content or ""
    messages.append(cast(MessageParam, response.choices[0].message))
    return content


def _build_relevant_files_section(relevant_files: list[tuple[str, str]]) -> str:
    if not relevant_files:
        return ""
    parts = ["Relevant file contents:"]
    for rel_path, content in relevant_files:
        parts.append(f"\n### {rel_path}\n```\n{content}\n```")
    return "\n".join(parts)


def _read_written_files(written_files: list[str], repo_root: str) -> str:
    parts: list[str] = []
    for rel_path in written_files:
        full_path = Path(repo_root) / rel_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            parts.append(f"### {rel_path}\n```\n{content}\n```")
        except OSError:
            parts.append(f"### {rel_path}\n(unreadable)")
    return "\n\n".join(parts)


def _write_docs(docs: dict[str, str], repo_root: str, sprint_slug: str) -> None:
    sprint_dir = Path(repo_root) / "docs" / "Sprints" / sprint_slug
    sprint_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in docs.items():
        (sprint_dir / filename).write_text(content, encoding="utf-8")
    console.print(f"[Sprint] Docs written to docs/Sprints/{sprint_slug}/")


def _load_existing_sprint_docs(repo_root: str, sprint_slug: str) -> tuple[str, str] | None:
    """Return (context, plan) if both already exist in docs/Sprints/{sprint_slug}/, else None."""
    sprint_dir = Path(repo_root) / "docs" / "Sprints" / sprint_slug
    context_file = sprint_dir / "CONTEXT.md"
    plan_file = sprint_dir / "PLAN.md"
    if context_file.exists() and plan_file.exists():
        return (
            context_file.read_text(encoding="utf-8"),
            plan_file.read_text(encoding="utf-8"),
        )
    return None


def run_sprint(
    issue: IssueCandidate,
    file_tree: str,
    relevant_files: list[tuple[str, str]],
    llm_client: LLMClient,
    repo_root: str,
    max_calls: int,
    max_file_bytes: int,
    model: str | None = None,
    sprint_slug: str = "",
) -> tuple[list[str], str]:
    """Run full sprint pipeline (study → context → plan → execute → review → junior summary).

    If CONTEXT.md and PLAN.md already exist in docs/Sprints/{sprint_slug}/, they are reused and
    the context/plan LLM phases are skipped — only study + execute are run.

    Writes sprint docs to docs/Sprints/{sprint_slug}/ in the repo.
    Returns (written_files, junior_summary).
    """
    existing = _load_existing_sprint_docs(repo_root, sprint_slug)

    # Always run a fresh study so the agent understands the current state of the codebase.
    messages: list[MessageParam] = [{"role": "system", "content": _PHASE_SYSTEM}]
    study = _chat_phase(
        messages,
        _STUDY_PROMPT.format(
            number=issue.number,
            title=issue.title,
            body=issue.body,
            file_tree=file_tree,
            relevant_files_section=_build_relevant_files_section(relevant_files),
        ),
        llm_client,
        model,
        "STUDY",
    )

    if existing:
        context, plan = existing
        console.print(
            f"[Sprint] Existing CONTEXT.md + PLAN.md found for '{sprint_slug}' — skipping context/plan phases."
        )
    else:
        context = _chat_phase(messages, _CONTEXT_PROMPT, llm_client, model, "CONTEXT")
        plan = _chat_phase(messages, _PLAN_PROMPT, llm_client, model, "PLAN")

    sprint_context = (
        f"## Sprint Study\n{study}\n\n"
        f"## Sprint Context\n{context}\n\n"
        f"## Sprint Plan\n{plan}"
    )

    # Execute phase — tool-calling loop with sprint context injected
    written_files = agentic_loop.run(
        issue=issue,
        file_tree=file_tree,
        relevant_files=relevant_files,
        llm_client=llm_client,
        repo_root=repo_root,
        max_calls=max_calls,
        max_file_bytes=max_file_bytes,
        model=model,
        sprint_context=sprint_context,
    )

    # Review phase — fresh conversation, reads written files
    review_messages: list[MessageParam] = [{"role": "system", "content": _REVIEW_SYSTEM}]
    review = _chat_phase(
        review_messages,
        _REVIEW_PROMPT.format(
            plan=plan,
            files_with_content=_read_written_files(written_files, repo_root),
        ),
        llm_client,
        model,
        "REVIEW",
    )

    # Junior summary — fresh conversation with full context
    junior_messages: list[MessageParam] = [{"role": "system", "content": _JUNIOR_SUMMARY_SYSTEM}]
    files_with_content = _read_written_files(written_files, repo_root)
    junior_summary = _chat_phase(
        junior_messages,
        _JUNIOR_SUMMARY_PROMPT.format(
            number=issue.number,
            title=issue.title,
            body=issue.body,
            study=study,
            plan=plan,
            written_files=", ".join(written_files) if written_files else "nenhum",
            files_with_content=files_with_content,
            review=review,
        ),
        llm_client,
        model,
        "JUNIOR SUMMARY",
    )

    docs = {
        "STUDY.md": study,
        "CONTEXT.md": context,
        "PLAN.md": plan,
        "REVIEW.md": review,
        "SUMMARY.md": junior_summary,
    }
    _write_docs(docs, repo_root, sprint_slug)

    return written_files, junior_summary
