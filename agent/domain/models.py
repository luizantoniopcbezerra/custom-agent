from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IssueCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    body: str
    score: int = Field(ge=1, le=10)
    reason: str
    repo_full_name: str
    created_at: str


class RepoConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner: str
    name: str
    branch: str = "main"
    labels: list[str] = Field(default_factory=list)
    exclude_labels: list[str] = Field(default_factory=list)
    max_issues_per_run: int = Field(default=1, ge=1)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class AgentRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    issue: IssueCandidate | None
    written_files: list[str]
    branch_name: str
    pr_url: str | None
    status: Literal["success", "noop", "error", "pending_pr"]
    error_message: str | None = None
    skip_reason: str | None = None
    junior_summary: str | None = None
