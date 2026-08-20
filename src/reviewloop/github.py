"""GitHub access layer: thin wrappers around the `gh` CLI and git.

Design note: the ONLY function that can push is commit_and_push(). Agent
workdirs have their push URL disabled right after checkout, so no agent --
whatever its prompt does -- can physically push. Permission design instead of
behavioral instructions."""

import json
import subprocess
from pathlib import Path

PUSH_DISABLED_URL = "no_push://disabled-by-reviewloop"


def _run(args: list[str], cwd: Path | str | None = None) -> str:
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _gh(args: list[str], cwd: Path | str | None = None) -> str:
    return _run(["gh", *args], cwd=cwd)


def _git(args: list[str], cwd: Path | str) -> str:
    return _run(["git", *args], cwd=cwd)


# --- reading PR state -------------------------------------------------------

def list_open_prs(repo: str) -> list[dict]:
    out = _gh(["pr", "list", "--repo", repo, "--json", "number,headRefName"])
    return json.loads(out)


def list_review_comments(repo: str, pr_number: int) -> list[dict]:
    out = _gh(["api", f"repos/{repo}/pulls/{pr_number}/comments", "--paginate"])
    return json.loads(out) if out else []


def actionable_comments(comments: list[dict], marker: str) -> list[dict]:
    """Thread roots that no reviewloop reply has handled yet."""
    handled_threads = {
        c.get("in_reply_to_id")
        for c in comments
        if c.get("in_reply_to_id") and marker in (c.get("body") or "")
    }
    return [
        c
        for c in comments
        if not c.get("in_reply_to_id")
        and c["id"] not in handled_threads
        and marker not in (c.get("body") or "")
    ]


# --- workdir management -----------------------------------------------------

def ensure_workdir(
    repo: str,
    pr_number: int,
    root: Path,
    git_name: str = "",
    git_email: str = "",
) -> Path:
    workdir = root / repo.replace("/", "__") / f"pr-{pr_number}"
    if not (workdir / ".git").exists():
        workdir.parent.mkdir(parents=True, exist_ok=True)
        _gh(["repo", "clone", repo, str(workdir)])
    if git_name:
        _git(["config", "user.name", git_name], cwd=workdir)
    if git_email:
        _git(["config", "user.email", git_email], cwd=workdir)
    _enable_push(workdir)  # gh pr checkout needs a working remote
    _git(["fetch", "origin"], cwd=workdir)
    _git(["checkout", "-f", "."], cwd=workdir)  # drop leftovers from a previous run
    _gh(["pr", "checkout", str(pr_number), "--force"], cwd=workdir)
    _git(["pull", "--ff-only"], cwd=workdir)
    disable_push(workdir)
    return workdir


def disable_push(workdir: Path) -> None:
    _git(["remote", "set-url", "--push", "origin", PUSH_DISABLED_URL], cwd=workdir)


def _enable_push(workdir: Path) -> None:
    fetch_url = _git(["remote", "get-url", "origin"], cwd=workdir)
    _git(["remote", "set-url", "--push", "origin", fetch_url], cwd=workdir)


def working_diff(workdir: Path) -> str:
    """Diff of everything the implementer changed, including new files."""
    _git(["add", "-A"], cwd=workdir)
    return _git(["diff", "--cached"], cwd=workdir)


def changed_files(workdir: Path) -> list[str]:
    out = _git(["diff", "--cached", "--name-only"], cwd=workdir)
    return [line for line in out.splitlines() if line]


# --- the single write path --------------------------------------------------

def commit_and_push(workdir: Path, message: str) -> str:
    _git(["commit", "-m", message], cwd=workdir)
    sha = _git(["rev-parse", "--short", "HEAD"], cwd=workdir)
    _enable_push(workdir)
    try:
        _git(["push"], cwd=workdir)
    finally:
        disable_push(workdir)
    return sha


def reply_to_comment(repo: str, pr_number: int, comment_id: int, body: str) -> None:
    _gh(
        [
            "api",
            "-X",
            "POST",
            f"repos/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
            "-f",
            f"body={body}",
        ]
    )
