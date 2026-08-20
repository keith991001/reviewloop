"""Runtime configuration. Everything is overridable via environment variables
so the public repo contains no personal or machine-specific values."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Target repository, "owner/name". Required at runtime.
    repo: str = field(default_factory=lambda: os.environ.get("REVIEWLOOP_REPO", ""))
    # Where PR branches get checked out and state files live.
    workdir_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("REVIEWLOOP_WORKDIR", "~/.cache/reviewloop")
        ).expanduser()
    )
    # Max implementer<->reviewer rounds before escalating to a human.
    max_rounds: int = field(
        default_factory=lambda: int(os.environ.get("REVIEWLOOP_MAX_ROUNDS", "3"))
    )
    # Commit identity used inside PR workdirs. If empty, the clone's own
    # git config applies -- set these to keep a consistent bot identity.
    git_name: str = field(default_factory=lambda: os.environ.get("REVIEWLOOP_GIT_NAME", ""))
    git_email: str = field(default_factory=lambda: os.environ.get("REVIEWLOOP_GIT_EMAIL", ""))
    # Marker prepended to every reply this system posts; also used to detect
    # already-handled comment threads.
    marker: str = "\U0001f916 reviewloop"

    @property
    def checkpoint_db(self) -> Path:
        return self.workdir_root / "checkpoints.sqlite"

    @property
    def pending_file(self) -> Path:
        return self.workdir_root / "pending.json"

    @property
    def log_file(self) -> Path:
        return self.workdir_root / "events.jsonl"


CONFIG = Config()
