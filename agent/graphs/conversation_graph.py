"""Conversation graph (one thread per client conversation).

load_thread -> classify_intent -> draft_reply -> liaison_compliance -> liaison_approval [interrupt]
  approve -> send_reply -> END | edit -> liaison_compliance | reject -> END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.graphs.bid_graph import RETRY
from agent.nodes.liaison import classify_intent, draft_reply, liaison_approval, liaison_compliance, load_thread, send_reply
from agent.state import ConversationState


def build(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    g.add_node("load_thread", load_thread, retry_policy=RETRY)
    g.add_node("classify_intent", classify_intent)
    g.add_node("draft_reply", draft_reply, retry_policy=RETRY)
    g.add_node("liaison_compliance", liaison_compliance)
    g.add_node("liaison_approval", liaison_approval)
    g.add_node("send_reply", send_reply, retry_policy=RETRY)
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", lambda s: "end" if s.get("status") == "dead_letter" else "go", {"go": "classify_intent", "end": END})
    g.add_edge("classify_intent", "draft_reply")
    g.add_edge("draft_reply", "liaison_compliance")
    g.add_conditional_edges("liaison_compliance", lambda s: "approval" if s.get("status") == "awaiting_approval" else "end",
                            {"approval": "liaison_approval", "end": END})
    g.add_conditional_edges("liaison_approval", lambda s: {"approved": "send", "edited": "comp"}.get(s.get("status", ""), "end"),
                            {"send": "send_reply", "comp": "liaison_compliance", "end": END})
    g.add_edge("send_reply", END)
    return g.compile(checkpointer=checkpointer, store=store)
