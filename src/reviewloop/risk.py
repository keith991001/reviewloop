"""Rule-based risk classifier for the final diff.

Deliberately NOT an LLM: the gate that decides whether a human must approve
should be deterministic, auditable, and cheap. Rules err on the side of
flagging; a human approval is a few seconds, a bad push is not."""

import re

# Path fragments that always require human approval when touched.
RISKY_PATH_PARTS = [
    "migrate",
    "migration",
    "auth",
    "secret",
    "credential",
    "payment",
    "billing",
    ".env",
    ".github/workflows",
]

# (compiled pattern, flag label) applied to added/removed lines of the diff.
RISKY_DIFF_PATTERNS = [
    (re.compile(r"\bDROP\s+(TABLE|COLUMN|DATABASE)\b", re.I), "sql-drop"),
    (re.compile(r"\bTRUNCATE\b", re.I), "sql-truncate"),
    (re.compile(r"\b(delete_all|destroy_all)\b"), "mass-delete"),
    (re.compile(r"\brm\s+-rf?\b"), "shell-rm"),
    (re.compile(r"\bchmod\s+777\b"), "world-writable"),
    (re.compile(r"(api[_-]?key|secret|token|password)\s*[=:]\s*['\"][^'\"]{8,}", re.I), "hardcoded-secret"),
]

LARGE_DELETION_THRESHOLD = 300


def classify(diff: str, files: list[str]) -> list[str]:
    flags: list[str] = []

    for path in files:
        lowered = path.lower()
        for part in RISKY_PATH_PARTS:
            if part in lowered:
                flags.append(f"path:{part}:{path}")

    changed_lines = [
        line for line in diff.splitlines() if line.startswith(("+", "-"))
    ]
    body = "\n".join(changed_lines)
    for pattern, label in RISKY_DIFF_PATTERNS:
        if pattern.search(body):
            flags.append(f"pattern:{label}")

    deletions = sum(1 for line in changed_lines if line.startswith("-"))
    if deletions > LARGE_DELETION_THRESHOLD:
        flags.append(f"large-deletion:{deletions}")

    return flags
