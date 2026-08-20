"""CLI entry points.

  reviewloop once             process new review comments, then exit
  reviewloop poll [--every N] keep polling
  reviewloop pending          list runs waiting for human risk approval
  reviewloop approve <thread> resume a paused run, allowing the push
  reviewloop reject <thread>  resume a paused run, discarding the change
"""

import argparse
import json
import sys
import time

from langgraph.types import Command

from . import github
from .config import CONFIG
from .graph import build_graph, default_checkpointer
from .log import log_event


def _load_pending() -> dict:
    if CONFIG.pending_file.exists():
        return json.loads(CONFIG.pending_file.read_text(encoding="utf-8"))
    return {}


def _save_pending(pending: dict) -> None:
    CONFIG.workdir_root.mkdir(parents=True, exist_ok=True)
    CONFIG.pending_file.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _require_repo() -> str:
    if not CONFIG.repo:
        sys.exit("REVIEWLOOP_REPO is not set (expected 'owner/name').")
    return CONFIG.repo


def _handle_result(thread_id: str, result: dict, pending: dict) -> None:
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        pending[thread_id] = payload
        _save_pending(pending)
        print(f"[reviewloop] PAUSED {thread_id}: risk flags {payload['flags']}")
        print(f"  approve with: reviewloop approve {thread_id}")
    else:
        pending.pop(thread_id, None)
        _save_pending(pending)
        print(f"[reviewloop] {thread_id}: {result.get('outcome', 'done')}")


def run_once(app) -> None:
    repo = _require_repo()
    pending = _load_pending()
    for pr in github.list_open_prs(repo):
        comments = github.list_review_comments(repo, pr["number"])
        for comment in github.actionable_comments(comments, CONFIG.marker):
            thread_id = f"pr{pr['number']}-c{comment['id']}"
            if thread_id in pending:
                continue  # waiting for a human decision
            log_event("trigger", pr=pr["number"], comment=comment["id"])
            result = app.invoke(
                {
                    "repo": repo,
                    "pr_number": pr["number"],
                    "branch": pr["headRefName"],
                    "comment_id": comment["id"],
                    "comment_body": comment["body"],
                    "comment_path": comment.get("path"),
                    "comment_line": comment.get("line"),
                },
                {"configurable": {"thread_id": thread_id}},
            )
            _handle_result(thread_id, result, pending)


def resume(app, thread_id: str, decision: str) -> None:
    pending = _load_pending()
    if thread_id not in pending:
        sys.exit(f"no pending run named {thread_id}")
    result = app.invoke(
        Command(resume=decision), {"configurable": {"thread_id": thread_id}}
    )
    _handle_result(thread_id, result, pending)


def main() -> None:
    parser = argparse.ArgumentParser(prog="reviewloop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once")
    poll = sub.add_parser("poll")
    poll.add_argument("--every", type=int, default=120, help="seconds between polls")
    sub.add_parser("pending")
    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("thread_id")
    args = parser.parse_args()

    if args.cmd == "pending":
        for thread_id, payload in _load_pending().items():
            print(f"{thread_id}: flags={payload['flags']}")
        return

    app = build_graph(checkpointer=default_checkpointer())

    if args.cmd == "once":
        run_once(app)
    elif args.cmd == "poll":
        while True:
            run_once(app)
            time.sleep(args.every)
    elif args.cmd in ("approve", "reject"):
        resume(app, args.thread_id, args.cmd)
