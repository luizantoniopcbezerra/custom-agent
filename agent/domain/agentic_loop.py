from __future__ import annotations

import json
from typing import cast

from openai import BadRequestError
from openai.types.chat import ChatCompletionMessageParam as MessageParam
from openai.types.chat import ChatCompletionToolMessageParam as ToolMessageParam
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from rich.console import Console

from agent.domain.models import IssueCandidate
from agent.domain.tools import TOOL_SCHEMAS, dispatch_tool
from agent.infrastructure.llm_client import LLMClient

console = Console()

SYSTEM_PROMPT = """\
You are an autonomous software engineer. You operate without human supervision.
Your only output is file changes committed as a PR — there is no one to review your reasoning mid-task.
This includes source code, configuration, tests, and documentation files depending on the issue type.

## Principles (non-negotiable)

**YAGNI**: implement exactly what the issue asks. Nothing more, nothing less.
**KISS**: choose the simplest correct solution. Clever is a liability when no one is watching.
**Less Code**: fewer lines, fewer files, fewer layers — without sacrificing correctness or clarity.
**Clean Code**: clear names, small functions, single responsibility, low coupling.
**Object Calisthenics**: one level of indentation per function; no else after return; wrap primitives with meaning; first-class collections; no getters/setters; small classes; no abbreviations.

## Decision rules for autonomous operation

- When in doubt between two approaches, pick the simpler one.
- Do not refactor code that is not directly related to the issue. Touch only what the issue requires.
- Do not add inline code comments or logging unless the issue explicitly asks for it.
- For `docs:` issues, writing documentation or markdown files IS the required output.
- Do not introduce new dependencies. Solve with what already exists in the codebase.
- If the issue is ambiguous, implement the most conservative interpretation that still resolves it.
- Never break existing behavior. Read tests and existing code before writing anything.
- Prefer early returns and linear flow over nested conditions.
- Reduce cyclomatic complexity: one thing per function, one reason to change per file.

## Tools available

- list_dir(path): list directory contents
- read_file(path): read a file inside the repository
- write_file(path, content): write the complete corrected file content (always full file, never partial)

## Workflow

1. Read the issue title and body carefully — understand the exact scope before touching any file.
2. Use list_dir(".") to map the repository structure.
3. Use read_file on the relevant files to understand the existing implementation.
4. Identify the minimal set of files that need to change to fix the issue.
5. Implement the fix with write_file — always write the complete file content.
6. When done, stop calling tools and write a short plain-text summary of what changed and why.

## Hard constraints

- Never write files outside the repository root.
- Never leave the codebase in a broken or partial state.
- When finished, respond with a plain-text summary and NO tool calls.
"""


def _build_initial_user_message(
    issue: IssueCandidate,
    file_tree: str,
    relevant_files: list[tuple[str, str]],
) -> str:
    parts: list[str] = [
        f"## Issue #{issue.number}: {issue.title}\n",
        f"{issue.body}\n",
        "## Repository File Tree\n",
        f"```\n{file_tree}\n```\n",
    ]
    for rel_path, content in relevant_files:
        parts.append(f"## {rel_path}\n\n```\n{content}\n```\n")
    return "\n".join(parts)


def _to_message_param(msg: object) -> MessageParam:
    """Convert assistant message to MessageParam, replacing malformed tool call args with '{}'.

    Some models (e.g. Nvidia free tier) occasionally emit invalid JSON in tool call arguments.
    Passing that raw message back to the provider on the next turn causes a 400. This function
    sanitises the arguments so the history stays valid while still returning an error to the model.
    """
    tool_calls = getattr(msg, "tool_calls", None)
    if not tool_calls:
        return cast(MessageParam, msg)

    sanitized: list[dict[str, object]] = []
    for tc in tool_calls:
        args = tc.function.arguments
        try:
            json.loads(args)
        except (json.JSONDecodeError, ValueError):
            args = "{}"
        sanitized.append(
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": args}}
        )

    return cast(
        MessageParam,
        {"role": "assistant", "content": getattr(msg, "content", None), "tool_calls": sanitized},
    )


def _process_tool_calls(
    tool_calls: list[ChatCompletionMessageToolCall],
    repo_root: str,
    written_files: list[str],
    max_bytes: int,
) -> list[ToolMessageParam]:
    results: list[ToolMessageParam] = []
    for call in tool_calls:
        result = dispatch_tool(call, repo_root, written_files, max_bytes)
        console.print(f"[AgenticLoop] tool={call.function.name} → {result[:80]}")
        results.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            }
        )
    return results


def run(
    issue: IssueCandidate,
    file_tree: str,
    relevant_files: list[tuple[str, str]],
    llm_client: LLMClient,
    repo_root: str,
    max_calls: int,
    max_file_bytes: int,
    model: str | None = None,
    sprint_context: str | None = None,
) -> list[str]:
    written_files: list[str] = []
    initial_user = _build_initial_user_message(issue, file_tree, relevant_files)
    if sprint_context:
        initial_user = f"{sprint_context}\n\n---\n\n{initial_user}"
    messages: list[MessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": initial_user},
    ]

    for i in range(max_calls):
        try:
            response = llm_client.chat(messages, TOOL_SCHEMAS, model=model)
        except BadRequestError as exc:
            console.print(f"[AgenticLoop] 400 from provider — stopping loop. ({exc})")
            break

        msg = response.choices[0].message
        messages.append(_to_message_param(msg))

        if not msg.tool_calls:
            console.print(
                f"[AgenticLoop] Done after {i + 1} turn(s). Files written: {written_files}"
            )
            break

        tool_results = _process_tool_calls(msg.tool_calls, repo_root, written_files, max_file_bytes)
        messages.extend(cast(list[MessageParam], tool_results))

    return written_files
