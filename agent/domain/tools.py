from __future__ import annotations

import contextlib
import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionToolParam

_MAX_LIST_ENTRIES = 200


def _guard_path(path: str, repo_root: str) -> str | None:
    try:
        resolved = os.path.realpath(os.path.join(repo_root, path))
    except ValueError:
        return None
    safe_root = os.path.realpath(repo_root)
    if resolved == safe_root or resolved.startswith(safe_root + os.sep):
        return resolved
    return None


def read_file(path: str, repo_root: str, max_bytes: int) -> str:
    resolved = _guard_path(path, repo_root)
    if resolved is None:
        return f"ERROR: path '{path}' is outside the repository root — access denied."
    try:
        with open(resolved, "rb") as fh:
            return fh.read(max_bytes).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return f"ERROR: file '{path}' not found."
    except OSError as exc:
        return f"ERROR: could not read '{path}': {exc}"


def write_file(
    path: str,
    content: str,
    repo_root: str,
    written_files: list[str],
) -> str:
    resolved = _guard_path(path, repo_root)
    if resolved is None:
        return f"ERROR: path '{path}' is outside the repository root — access denied."
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        with open(resolved, "w", encoding="utf-8") as fh:
            fh.write(content)
        written_files.append(path)
        return "ok"
    except OSError as exc:
        return f"ERROR: could not write '{path}': {exc}"


def list_dir(path: str, repo_root: str) -> str:
    resolved = _guard_path(path, repo_root)
    if resolved is None:
        return f"ERROR: path '{path}' is outside the repository root — access denied."
    try:
        entries: list[dict[str, object]] = []
        with os.scandir(resolved) as it:
            for entry in it:
                if len(entries) >= _MAX_LIST_ENTRIES:
                    break
                size: int | None = None
                if entry.is_file(follow_symlinks=False):
                    kind = "file"
                    with contextlib.suppress(OSError):
                        size = entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    kind = "dir"
                else:
                    kind = "other"
                entries.append({"name": entry.name, "type": kind, "size": size})
        return json.dumps(entries, ensure_ascii=False)
    except FileNotFoundError:
        return f"ERROR: directory '{path}' not found."
    except OSError as exc:
        return f"ERROR: could not list '{path}': {exc}"


def dispatch_tool(
    tool_call: object,
    repo_root: str,
    written_files: list[str],
    max_bytes: int,
) -> str:
    name: str = tool_call.function.name  # type: ignore[attr-defined]
    try:
        args: dict[str, object] = json.loads(tool_call.function.arguments)  # type: ignore[attr-defined]
    except (json.JSONDecodeError, AttributeError):
        return "ERROR: could not parse tool arguments."

    if name == "read_file":
        return read_file(str(args.get("path", "")), repo_root, max_bytes)
    if name == "write_file":
        return write_file(
            str(args.get("path", "")),
            str(args.get("content", "")),
            repo_root,
            written_files,
        )
    if name == "list_dir":
        return list_dir(str(args.get("path", ".")), repo_root)

    return f"ERROR: unknown tool '{name}'."


TOOL_SCHEMAS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file inside the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from the repository root, e.g. 'src/main.py'.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (create or overwrite) a file inside the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from the repository root, e.g. 'src/main.py'.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file.",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the contents of a directory inside the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from the repository root. Defaults to '.' (root).",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]
