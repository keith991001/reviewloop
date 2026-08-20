"""Shared state flowing through the LangGraph state machine."""

from typing import TypedDict


class LoopState(TypedDict, total=False):
    repo: str
    pr_number: int
    branch: str
    workdir: str
    # The review comment being addressed.
    comment_id: int
    comment_body: str
    comment_path: str
    comment_line: int | None
    # Implementer <-> reviewer loop.
    rounds: int
    diff: str
    review_passed: bool
    reviewer_feedback: str
    # Risk gate.
    risk_flags: list[str]
    # Terminal result: "pushed" | "escalated" | "aborted".
    outcome: str
