"""State machine tests with the LLM and GitHub layers mocked out.

These verify the orchestration contract itself: routing, the retry loop,
and the interrupt/resume cycle -- the parts that must be deterministic."""

from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from reviewloop.graph import build_graph

INITIAL = {
    "repo": "example/demo",
    "pr_number": 1,
    "branch": "feature",
    "comment_id": 100,
    "comment_body": "Please fix the rounding bug",
    "comment_path": "app/models/price.rb",
    "comment_line": 10,
}


@pytest.fixture
def env():
    patches = {
        "workdir": patch("reviewloop.nodes.github.ensure_workdir", return_value="/tmp/fake"),
        "impl": patch("reviewloop.agents.run_implementer", return_value="done"),
        "diff": patch("reviewloop.nodes.github.working_diff", return_value="+ safe change"),
        "files": patch("reviewloop.nodes.github.changed_files", return_value=["app/models/price.rb"]),
        "rulebook": patch("reviewloop.nodes.RULEBOOK_PATH"),
        "push": patch("reviewloop.nodes.github.commit_and_push", return_value="abc1234"),
        "reply": patch("reviewloop.nodes.github.reply_to_comment"),
        "review": patch("reviewloop.agents.run_reviewer"),
        "log": patch("reviewloop.nodes.log_event"),
    }
    mocks = {name: p.start() for name, p in patches.items()}
    mocks["rulebook"].read_text.return_value = "- R001 no floats for money"
    yield mocks
    for p in patches.values():
        p.stop()


def invoke(state_or_cmd, thread="t1"):
    app = build_graph(checkpointer=MemorySaver())
    return app, app.invoke(state_or_cmd, {"configurable": {"thread_id": thread}})


def test_pass_first_round_pushes(env):
    env["review"].return_value = {"pass": True, "issues": []}
    _, result = invoke(INITIAL)
    assert result["outcome"] == "pushed"
    assert result["rounds"] == 1
    env["push"].assert_called_once()


def test_reject_then_pass_loops_twice(env):
    env["review"].side_effect = [
        {"pass": False, "issues": ["price.rb: still uses float (R001)"]},
        {"pass": True, "issues": []},
    ]
    _, result = invoke(INITIAL)
    assert result["outcome"] == "pushed"
    assert result["rounds"] == 2
    # Second implementer call must carry the reviewer's feedback.
    feedback_arg = env["impl"].call_args_list[1].args[4]
    assert "R001" in feedback_arg


def test_exhausted_rounds_escalate(env):
    env["review"].return_value = {"pass": False, "issues": ["never good enough"]}
    _, result = invoke(INITIAL)
    assert result["outcome"] == "escalated"
    assert result["rounds"] == 3  # CONFIG.max_rounds default
    env["push"].assert_not_called()
    env["reply"].assert_called_once()  # escalation notice posted


def test_risky_diff_pauses_then_approve_pushes(env):
    env["review"].return_value = {"pass": True, "issues": []}
    env["diff"].return_value = "+ DROP TABLE users;"
    app = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "risky"}}

    paused = app.invoke(INITIAL, cfg)
    assert "__interrupt__" in paused
    assert any("sql-drop" in f for f in paused["__interrupt__"][0].value["flags"])
    env["push"].assert_not_called()

    resumed = app.invoke(Command(resume="approve"), cfg)
    assert resumed["outcome"] == "pushed"
    env["push"].assert_called_once()


def test_risky_diff_rejected_aborts(env):
    env["review"].return_value = {"pass": True, "issues": []}
    env["diff"].return_value = "+ rm -rf /data"
    app = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "rejected"}}

    app.invoke(INITIAL, cfg)
    result = app.invoke(Command(resume="reject"), cfg)
    assert result["outcome"] == "aborted"
    env["push"].assert_not_called()
