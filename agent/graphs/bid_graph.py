"""Bid graph (one thread per job), hand-written StateGraph.

intake -> Send(analyst | risk | matcher)  [parallel]  -> decide
  decide: skip/watch -> END | bid -> pricing -> writer -> verifier -> critic
  critic: revise (<= max_revisions) -> writer | ok -> compliance
  compliance: blocked -> END (needs_attention) | ok -> approval [interrupt]
  approval: approve -> submit -> END | edit -> compliance -> approval | reject -> END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent.nodes.analyst import analyst
from agent.nodes.approval import approval, submit
from agent.nodes.compliance import compliance
from agent.nodes.critic import after_critic, critic, verifier
from agent.nodes.decide import decide
from agent.nodes.matcher import matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk import risk
from agent.nodes.scout import intake
from agent.nodes.writer import writer
from agent.state import BidState

RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2.0,
                    retry_on=lambda e: isinstance(e, (TimeoutError, ConnectionError, OSError)))


def fan_out(state: dict):
    if state.get("status") in ("dead_letter", "needs_attention"):
        return END
    return [Send("analyst", state), Send("risk", state), Send("matcher", state)]


def after_decide(state: dict) -> str:
    if state.get("status") == "needs_attention":
        return "end"
    return "bid" if state["decision"]["action"] == "bid" else "end"


def after_compliance(state: dict) -> str:
    return "approval" if state.get("status") == "awaiting_approval" else "end"


def after_approval(state: dict) -> str:
    return {"approved": "submit", "edited": "compliance"}.get(state.get("status", ""), "end")


def build(checkpointer=None, store=None):
    g = StateGraph(BidState)
    g.add_node("intake", intake, retry_policy=RETRY)
    g.add_node("analyst", analyst, retry_policy=RETRY)
    g.add_node("risk", risk, retry_policy=RETRY)
    g.add_node("matcher", matcher, retry_policy=RETRY)
    g.add_node("decide", decide)
    g.add_node("pricing", pricing, retry_policy=RETRY)
    g.add_node("writer", writer, retry_policy=RETRY)
    g.add_node("verifier", verifier, retry_policy=RETRY)
    g.add_node("critic", critic, retry_policy=RETRY)
    g.add_node("compliance", compliance)
    g.add_node("approval", approval)
    g.add_node("submit", submit, retry_policy=RETRY)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk", "matcher", END])
    for n in ("analyst", "risk", "matcher"):
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", after_decide, {"bid": "pricing", "end": END})
    g.add_edge("pricing", "writer")
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, {"revise": "writer", "compliance": "compliance", "end": END})
    g.add_conditional_edges("compliance", after_compliance, {"approval": "approval", "end": END})
    g.add_conditional_edges("approval", after_approval, {"submit": "submit", "compliance": "compliance", "end": END})
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store)
