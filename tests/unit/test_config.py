import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.config import AgentConfig, AgentSettings, OpenRouterConfig


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yml"
    p.write_text(textwrap.dedent(content))
    return p


def test_from_yaml_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("GH_TOKEN", "ghp_test")

    yaml_path = _write_yaml(
        tmp_path,
        """
        openrouter:
          model: "qwen/qwen3-coder:free"
          max_requests_per_minute: 15
        agent:
          difficulty_threshold: 4
        repos:
          - owner: alice
            name: my-repo
            branch: main
        """,
    )
    config = AgentConfig.from_yaml(yaml_path)

    assert config.openrouter.model == "qwen/qwen3-coder:free"
    assert config.openrouter.max_requests_per_minute == 15
    assert config.agent.difficulty_threshold == 4
    assert len(config.repos) == 1
    assert config.repos[0].full_name == "alice/my-repo"


def test_missing_openrouter_api_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GH_TOKEN", "ghp_test")

    yaml_path = _write_yaml(tmp_path, "repos: []")
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY is required"):
        AgentConfig.from_yaml(yaml_path)


def test_missing_gh_token_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("GH_TOKEN", raising=False)

    yaml_path = _write_yaml(tmp_path, "repos: []")
    with pytest.raises(ValidationError, match="GH_TOKEN is required"):
        AgentConfig.from_yaml(yaml_path)


def test_env_var_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    monkeypatch.setenv("GH_TOKEN", "ghp_from-env")

    yaml_path = _write_yaml(tmp_path, "repos: []")
    config = AgentConfig.from_yaml(yaml_path)

    assert config.openrouter_api_key == "sk-from-env"
    assert config.gh_token == "ghp_from-env"


def test_dry_run_defaults_to_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    monkeypatch.delenv("AGENT_DRY_RUN", raising=False)

    yaml_path = _write_yaml(tmp_path, "repos: []")
    config = AgentConfig.from_yaml(yaml_path)
    assert config.dry_run is False


def test_dry_run_env_var_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    monkeypatch.setenv("AGENT_DRY_RUN", "true")

    yaml_path = _write_yaml(tmp_path, "repos: []")
    config = AgentConfig.from_yaml(yaml_path)
    assert config.dry_run is True


def test_openrouter_config_defaults() -> None:
    cfg = OpenRouterConfig()
    assert cfg.model == "qwen/qwen3-coder:free"
    assert cfg.max_requests_per_minute == 18
    assert cfg.max_requests_per_day == 45


def test_agent_settings_defaults() -> None:
    s = AgentSettings()
    assert s.max_tool_calls_per_issue == 30
    assert s.difficulty_threshold == 5
