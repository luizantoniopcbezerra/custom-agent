import os

import pytest

from agent.domain.context_builder import (
    build_file_tree,
    extract_keywords,
    select_relevant_files,
)


def _create_repo(tmp_path: pytest.TempPathFactory, structure: dict[str, str]) -> str:
    root = str(tmp_path)
    for rel_path, content in structure.items():
        abs_path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root


def test_build_file_tree_excludes_git_dir(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(
        tmp_path,
        {
            "src/main.py": "print('hello')",
            ".git/config": "[core]",
            ".git/HEAD": "ref: refs/heads/main",
        },
    )
    tree = build_file_tree(root)
    assert "main.py" in tree
    assert ".git" not in tree


def test_build_file_tree_excludes_node_modules(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(
        tmp_path,
        {
            "index.js": "module.exports = {}",
            "node_modules/lodash/index.js": "module.exports = {}",
        },
    )
    tree = build_file_tree(root)
    assert "index.js" in tree
    assert "node_modules" not in tree


def test_build_file_tree_truncates_at_400_lines(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "src"), exist_ok=True)
    for i in range(500):
        with open(os.path.join(root, "src", f"file_{i:04d}.py"), "w") as fh:
            fh.write(f"# file {i}")

    tree = build_file_tree(root)
    lines = tree.splitlines()
    assert lines[-1] == "... (truncated)"
    assert len(lines) <= 401  # 400 entries + truncation marker


def test_extract_keywords_filters_stopwords() -> None:
    keywords = extract_keywords("Fix the bug", "the function was not working")
    assert "the" not in keywords
    assert "was" not in keywords
    assert "function" in keywords
    assert "working" in keywords


def test_extract_keywords_filters_short_tokens() -> None:
    keywords = extract_keywords("Fix it now", "add the fix")
    assert "Fix" not in keywords
    assert "fix" not in keywords
    assert "it" not in keywords
    assert "add" not in keywords


def test_extract_keywords_returns_unique_lowercased() -> None:
    keywords = extract_keywords("Login Login login", "Login issue")
    assert keywords.count("login") == 1


def test_select_relevant_files_ranks_by_relevance(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(
        tmp_path,
        {
            "auth/login.py": "def login(): pass  # authentication login handler",
            "utils/string_helper.py": "def trim(): pass",
            "README.md": "# Project",
        },
    )
    keywords = ["login", "authentication"]
    result = select_relevant_files(root, keywords, max_files=3, max_bytes=50_000)
    paths = [r[0] for r in result]
    assert paths[0] in {"auth/login.py", "auth\\login.py"}


def test_select_relevant_files_respects_max_files(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(
        tmp_path,
        {
            "a.py": "hello world",
            "b.py": "hello world",
            "c.py": "hello world",
        },
    )
    result = select_relevant_files(root, [], max_files=2, max_bytes=50_000)
    assert len(result) == 2


def test_select_relevant_files_respects_max_bytes(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(tmp_path, {"big.py": "x" * 1000})
    result = select_relevant_files(root, [], max_files=5, max_bytes=100)
    assert len(result) == 1
    content = result[0][1]
    assert len(content) <= 100


def test_build_file_tree_excludes_binary_extensions(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(tmp_path, {"app.py": "pass"})
    with open(os.path.join(root, "logo.png"), "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    tree = build_file_tree(root)
    assert "app.py" in tree
    assert "logo.png" not in tree


def test_build_file_tree_excludes_deep_node_modules(tmp_path: pytest.TempPathFactory) -> None:
    root = _create_repo(
        tmp_path,
        {
            "app.py": "pass",
            "node_modules/react/dist/react.js": "module.exports = {}",
            "node_modules/lodash/fp/array.js": "module.exports = []",
        },
    )
    tree = build_file_tree(root)
    assert "react.js" not in tree
    assert "array.js" not in tree
    assert "app.py" in tree
