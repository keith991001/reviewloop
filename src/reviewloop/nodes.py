"""Graph nodes. Each is a plain function: state in, partial state update out.
All side effects (git, gh, LLM calls) live behind github.py / agents.py."""

from pathlib import Path

from langgraph.types import interrupt

from . import agents, github, risk
from .config import CONFIG
from .log import log_event
from .state import LoopState

RULEBOOK_PATH = Path(__file__).resolve().parents[2] / "rulebook" / "rules.md"


def prepare(state: LoopState) -> dict:
    workdir = github.ensure_workdir(
        state["repo"],
        state["pr_number"],
        CONFIG.workdir_root,
        CONFIG.git_name,
        CONFIG.git_email,
    )
    log_event("prepare", pr=state["pr_number"], comment=state["comment_id"])
    return {"workdir": str(workdir), "rounds": 0}


def implement(state: LoopState) -> dict:
    workdir = Path(state["workdir"])
    summary = agents.run_implementer(
        workdir,
        state["comment_body"],
        state.get("comment_path"),
        state.get("comment_line"),
        state.get("reviewer_feedback", ""),
    )
    diff = github.working_diff(workdir)
    rounds = state.get("rounds", 0) + 1
    log_event(
        "implement",
        pr=state["pr_number"],
        comment=state["comment_id"],
        round=rounds,
        diff_bytes=len(diff),
        summary=summary[:300],
    )
    return {"diff": diff, "rounds": rounds}


def review(state: LoopState) -> dict:
    rulebook = RULEBOOK_PATH.read_text(encoding="utf-8")
    verdict = agents.run_reviewer(Path(state["workdir"]), state["diff"], rulebook)
    log_event(
        "review",
        pr=state["pr_number"],
        comment=state["comment_id"],
        round=state["rounds"],
        passed=verdict["pass"],
        issues=verdict["issues"],
    )
    return {
        "review_passed": bool(verdict["pass"]),
        "reviewer_feedback": "\n".join(verdict["issues"]),
    }


def route_after_review(state: LoopState) -> str:
    if state["review_passed"]:
        return "risk_gate"
    if state["rounds"] >= CONFIG.max_rounds:
        return "escalate"
    return "implement"


def risk_gate(state: LoopState) -> dict:
    workdir = Path(state["workdir"])
    flags = risk.classify(state["diff"], github.changed_files(workdir))
    log_event("risk_gate", pr=state["pr_number"], comment=state["comment_id"], flags=flags)
    if not flags:
        return {"risk_flags": []}
    # Pause here: state is checkpointed, the process may exit. A human
    # resumes with Command(resume="approve"|"reject") via the CLI.
    decision = interrupt(
        {
            "pr_number": state["pr_number"],
            "comment_id": state["comment_id"],
            "flags": flags,
            "diff_preview": state["diff"][:3000],
        }
    )
    log_event("human_decision", pr=state["pr_number"], comment=state["comment_id"], decision=decision)
    if decision != "approve":
        return {"risk_flags": flags, "outcome": "aborted"}
    return {"risk_flags": flags}


def route_after_gate(state: LoopState) -> str:
    return "abort" if state.get("outcome") == "aborted" else "push"


def push(state: LoopState) -> dict:
    workdir = Path(state["workdir"])
    sha = github.commit_and_push(
        workdir, f"Address review comment (round {state['rounds']})"
    )
    body = (
        f"{CONFIG.marker} pushed {sha} after {state['rounds']} internal "
        f"review round(s)."
    )
    if state["risk_flags"]:
        body += f" Human-approved risk flags: {', '.join(state['risk_flags'])}."
    github.reply_to_comment(state["repo"], state["pr_number"], state["comment_id"], body)
    log_event("push", pr=state["pr_number"], comment=state["comment_id"], sha=sha)
    return {"outcome": "pushed"}


def escalate(state: LoopState) -> dict:
    body = (
        f"{CONFIG.marker} escalating to a human: internal reviewer still "
        f"rejects after {state['rounds']} rounds.\nOpen points:\n"
        f"{state['reviewer_feedback']}"
    )
    github.reply_to_comment(state["repo"], state["pr_number"], state["comment_id"], body)
    log_event("escalate", pr=state["pr_number"], comment=state["comment_id"])
    return {"outcome": "escalated"}


def abort(state: LoopState) -> dict:
    body = (
        f"{CONFIG.marker} change discarded: a human rejected the risk "
        f"flags ({', '.join(state['risk_flags'])})."
    )
    github.reply_to_comment(state["repo"], state["pr_number"], state["comment_id"], body)
    log_event("abort", pr=state["pr_number"], comment=state["comment_id"])
    return {"outcome": "aborted"}
