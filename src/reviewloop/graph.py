"""State machine wiring. The graph mirrors docs/design.md section 3."""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from . import nodes
from .config import CONFIG
from .state import LoopState


def build_graph(checkpointer=None):
    g = StateGraph(LoopState)

    g.add_node("prepare", nodes.prepare)
    g.add_node("implement", nodes.implement)
    g.add_node("review", nodes.review)
    g.add_node("risk_gate", nodes.risk_gate)
    g.add_node("push", nodes.push)
    g.add_node("escalate", nodes.escalate)
    g.add_node("abort", nodes.abort)

    g.add_edge(START, "prepare")
    g.add_edge("prepare", "implement")
    g.add_edge("implement", "review")
    g.add_conditional_edges(
        "review",
        nodes.route_after_review,
        {"risk_gate": "risk_gate", "implement": "implement", "escalate": "escalate"},
    )
    g.add_conditional_edges(
        "risk_gate",
        nodes.route_after_gate,
        {"push": "push", "abort": "abort"},
    )
    g.add_edge("push", END)
    g.add_edge("escalate", END)
    g.add_edge("abort", END)

    return g.compile(checkpointer=checkpointer)


def default_checkpointer() -> SqliteSaver:
    CONFIG.workdir_root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CONFIG.checkpoint_db), check_same_thread=False)
    return SqliteSaver(conn)
