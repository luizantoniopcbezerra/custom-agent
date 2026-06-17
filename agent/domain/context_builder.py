from __future__ import annotations

import json
import os
import re

IGNORE_DIRS: frozenset[str] = frozenset(
    [
        ".git",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "htmlcov",
        ".tox",
    ]
)

IGNORE_EXTENSIONS: frozenset[str] = frozenset(
    [
        ".pyc",
        ".pyo",
        ".so",
        ".dylib",
        ".exe",
        ".bin",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".whl",
        ".egg",
    ]
)

_MAX_TREE_LINES = 400

STOPWORDS: frozenset[str] = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "have",
        "from",
        "not",
        "are",
        "was",
        "were",
        "been",
        "will",
        "when",
        "what",
        "which",
        "also",
        "can",
        "just",
        "into",
        "more",
        "some",
        "then",
        "than",
        "like",
        "how",
        "para",
        "com",
        "que",
        "uma",
        "isso",
        "este",
        "esse",
        "como",
        "mais",
        "não",
        "mas",
        "por",
        "ser",
        "tem",
        "aqui",
        "fazer",
    ]
)


def _should_ignore_dir(name: str) -> bool:
    if name in IGNORE_DIRS:
        return True
    return bool(name.endswith(".egg-info"))


def _is_binary(path: str) -> bool:
    _, ext = os.path.splitext(path)
    if ext.lower() in IGNORE_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(512)
        chunk.decode("utf-8")
        return False
    except (UnicodeDecodeError, OSError):
        return True


def build_file_tree(repo_path: str) -> str:
    lines: list[str] = []
    root = os.path.realpath(repo_path)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_ignore_dir(d)]

        rel_dir = os.path.relpath(dirpath, root)
        prefix = "" if rel_dir == "." else rel_dir + "/"

        for filename in sorted(filenames):
            _, ext = os.path.splitext(filename)
            if ext.lower() in IGNORE_EXTENSIONS:
                continue
            lines.append(prefix + filename)
            if len(lines) >= _MAX_TREE_LINES:
                lines.append("... (truncated)")
                return "\n".join(lines)

    return "\n".join(lines)


def extract_keywords(title: str, body: str) -> list[str]:
    combined = (title + " " + body).lower()
    tokens = re.split(r"[\s\W_]+", combined)
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if len(token) <= 3:
            continue
        if token in STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _score_file(file_path: str, first_bytes: str, keywords: list[str]) -> int:
    combined = (file_path + " " + first_bytes).lower()
    return sum(1 for kw in keywords if kw in combined)


def select_relevant_files(
    repo_path: str,
    keywords: list[str],
    max_files: int,
    max_bytes: int,
) -> list[tuple[str, str]]:
    root = os.path.realpath(repo_path)
    scored: list[tuple[int, str]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_ignore_dir(d)]
        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            _, ext = os.path.splitext(filename)
            if ext.lower() in IGNORE_EXTENSIONS:
                continue
            rel_path = os.path.relpath(abs_path, root)
            try:
                with open(abs_path, "rb") as fh:
                    raw = fh.read(200)
                first_bytes = raw.decode("utf-8", errors="replace")
            except OSError:
                continue
            score = _score_file(rel_path, first_bytes, keywords)
            scored.append((score, rel_path))

    scored.sort(key=lambda x: x[0], reverse=True)
    result: list[tuple[str, str]] = []
    for _, rel_path in scored[:max_files]:
        abs_path = os.path.join(root, rel_path)
        try:
            with open(abs_path, "rb") as fh:
                content = fh.read(max_bytes).decode("utf-8", errors="replace")
        except OSError:
            continue
        result.append((rel_path, content))

    return result


def build_context_summary(
    file_tree: str,
    relevant_files: list[tuple[str, str]],
) -> str:
    parts: list[str] = [f"## File Tree\n\n{file_tree}\n"]
    for rel_path, content in relevant_files:
        parts.append(f"## {rel_path}\n\n```\n{content}\n```\n")
    return "\n".join(parts)


def list_to_json(entries: list[dict[str, object]]) -> str:
    return json.dumps(entries, ensure_ascii=False)
