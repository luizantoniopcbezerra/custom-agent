from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.domain.models import RepoConfig


class OpenRouterConfig(BaseModel):
    model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    max_requests_per_minute: int = Field(default=18, ge=1)
    max_requests_per_day: int = Field(default=45, ge=1)


class AgentSettings(BaseModel):
    max_tool_calls_per_issue: int = Field(default=30, ge=1)
    max_file_size_bytes: int = Field(default=50_000, ge=1)
    max_context_files: int = Field(default=10, ge=1)
    difficulty_threshold: int = Field(default=5, ge=1, le=10)
    conventional_types: list[str] = Field(default_factory=list)
    max_resolutions_per_run: int = Field(default=3, ge=1)


class AccountConfig(BaseModel):
    token_env: str  # name of the env var containing this account's GH token


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_nested_delimiter="__",
        extra="ignore",
    )

    openrouter_api_key: str = ""
    gh_token: str = ""
    dry_run: bool = Field(
        default=False,
        validation_alias=AliasChoices("dry_run", "agent_dry_run"),
    )
    email_from: str = ""
    email_app_password: str = ""
    email_to: str = ""
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    repos: list[RepoConfig] = Field(default_factory=list)
    accounts: list[AccountConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_secrets(self) -> AgentConfig:
        if not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required. Set it in .env or as an environment variable."
            )
        if not self.accounts and not self.gh_token:
            raise ValueError(
                "GH_TOKEN is required when 'accounts' is not configured. "
                "Set it in .env or as an environment variable."
            )
        return self

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_from and self.email_app_password and self.email_to)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AgentConfig:
        raw: dict[str, Any] = {}
        yaml_path = Path(path)
        if yaml_path.exists():
            with yaml_path.open() as fh:
                raw = yaml.safe_load(fh) or {}

        openrouter_raw = raw.pop("openrouter", {})
        agent_raw = raw.pop("agent", {})
        repos_raw = raw.pop("repos", [])
        accounts_raw = raw.pop("accounts", [])

        return cls(
            **raw,
            openrouter=OpenRouterConfig(**openrouter_raw),
            agent=AgentSettings(**agent_raw),
            repos=[RepoConfig(**r) for r in repos_raw],
            accounts=[AccountConfig(**a) for a in accounts_raw],
        )
