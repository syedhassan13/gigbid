"""Typed graph state (C2). Three things kept apart:

* State      - what this job / conversation needs right now (fields below).
* Trace      - `trace`: every tool name, args, result and observation (append-only reducer),
               persisted with the checkpoint for audit/debugging and shown in the run viewer.
* Long-term memory - NOT here: only promoted knowledge in the LangGraph store (agent/memory).
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def add_int(a: int | None, b: int | None) -> int:
    """Budget counter. A negative update RESETS it: every fresh run on a thread starts a new step/token budget."""
    if b is not None and b < 0:
        return 0
    return (a or 0) + (b or 0)


class BidState(TypedDict, total=False):
    # inputs
    user_id: str
    persona: str
    job_id: str
    trace_id: str
    autonomy: str
    force_bid: bool                                 # user clicked "bid anyway" (never overrides a scam verdict)
    # state
    job: dict
    client: dict
    analyses: Annotated[dict, merge_dict]          # parallel branches write job_spec / risk / fit here
    decision: dict
    price: dict
    draft: dict
    verification: dict
    critiques: Annotated[list, operator.add]
    revisions: int
    compliance: dict
    preview: dict
    approval: dict
    submission: dict
    status: str                                     # analysing | skipped | awaiting_approval | submitted | rejected | needs_attention | dead_letter
    error: str
    # execution trace + budgets
    trace: Annotated[list, operator.add]
    steps: Annotated[int, add_int]
    tokens: Annotated[int, add_int]
    cost_usd: Annotated[float, operator.add]
    outcome: dict


class ConversationState(TypedDict, total=False):
    user_id: str
    persona: str
    thread_id: str
    trace_id: str
    messages: list
    job: dict
    intent: dict
    slots: list
    draft: dict
    compliance: dict
    approval: dict
    sent: dict
    status: str
    trace: Annotated[list, operator.add]
    steps: Annotated[int, add_int]
    tokens: Annotated[int, add_int]
    cost_usd: Annotated[float, operator.add]


def trace_event(node: str, kind: str, **data: Any) -> list[dict]:
    import time
    from agent.tracing import mask_obj
    return [{"ts": time.time(), "node": node, "kind": kind, **mask_obj(data)}]
