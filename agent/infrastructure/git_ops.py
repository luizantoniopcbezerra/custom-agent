import re
import shutil

from git import GitCommandError, Repo
from rich.console import Console

console = Console()


class BranchAlreadyExistsError(RuntimeError):
    """Raised when the target branch already exists locally or on the remote."""


def _mask_token(url: str) -> str:
    return re.sub(r"x-access-token:[^@]+@", "x-access-token:***@", url)


def clone(owner: str, name: str, token: str, tmp_dir: str) -> Repo:
    """Clone a GitHub repo into tmp_dir using a PAT embedded in the URL."""
    url = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    console.print(f"[Git] Cloning {_mask_token(url)} → {tmp_dir}")
    return Repo.clone_from(url, tmp_dir)


def commit_and_push(repo: Repo, branch_name: str, commit_msg: str, create: bool = True) -> None:
    """Stage all changes, commit, and push. Creates branch when create=True."""
    if create:
        try:
            repo.git.checkout("-b", branch_name)
        except GitCommandError as exc:
            if "already exists" in str(exc).lower():
                raise BranchAlreadyExistsError(
                    f"Branch '{branch_name}' already exists locally."
                ) from exc
            raise
    else:
        repo.git.checkout(branch_name)

    repo.git.add("-A")
    repo.index.commit(commit_msg)

    try:
        repo.remote("origin").push(refspec=f"HEAD:{branch_name}")
    except GitCommandError as exc:
        if create and "already exists" in str(exc).lower():
            raise BranchAlreadyExistsError(
                f"Branch '{branch_name}' already exists on the remote."
            ) from exc
        raise

    console.print(f"[Git] Pushed branch '{branch_name}'")


def cleanup(repo: Repo, tmp_dir: str) -> None:
    """Close the repo handle and remove the temporary directory."""
    repo.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)
