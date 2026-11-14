"""Human approval (C5, R4) + exactly-once submit (C6).

approval: builds the dry-run preview through the Marketplace MCP server
          (create_proposal_draft -> cost, balance after, violations), then interrupt()s
          with the draft, the evidence behind every claim, the risk report, the price
          rationale and the preview. The UI resumes the thread with approve | edit | reject.
submit:   separate node, so a crash after approval re-executes ONLY the submit; the
          idempotency key is derived from (thread, draft) => the marketplace never
          submits or spends Connects twice.
"""
from __future__ import annotations

import hashlib

from langgraph.types import interrupt

from agent.handoffs import Approval
from agent.mcp_client import ServerUnavailable
from agent.memory.promotion_rules import observe_edit
from agent.nodes.base import cfg_val, node
from agent.state import trace_event


def idem_key(thread_id: str, text: str, kind: str) -> str:
    return f"{kind}-{hashlib.sha256((thread_id + '|' + text).encode()).hexdigest()[:32]}"


@node("approval", timeout=86400 * 30)
async def approval(state: dict, cfg: dict, store) -> dict:
    port = cfg_val(cfg, "port")
    thread_id = cfg["configurable"]["thread_id"]
    d = state["draft"]
    payload = {"job_id": state["job"]["id"], "cover_letter": d["cover_letter"], "bid_amount": state["price"]["amount"],
               "screening_answers": d.get("screening_answers", []), "variant": d.get("variant")}
    key = idem_key(thread_id, d["cover_letter"] + str(state["price"]["amount"]), "draft")
    try:
        draft_res = await port.create_draft(payload, key)
    except ServerUnavailable as e:
        return {"status": "dead_letter", "error": f"marketplace unavailable while preparing preview: {e.detail}",
                "trace": trace_event("approval", "degraded", error=str(e))}
    preview = draft_res["preview"]
    decision = interrupt({
        "type": "proposal_approval",
        "job": {k: state["job"].get(k) for k in ("id", "title", "budget_type", "budget_min", "budget_max", "connects_cost")},
        "draft": d, "citations": d.get("citations", []), "verification": state.get("verification", {}),
        "risk": state["analyses"]["risk"], "fit": state["analyses"]["fit"], "price": state["price"],
        "compliance": state.get("compliance", {}), "critiques": state.get("critiques", []), "dry_run": preview,
        "draft_id": draft_res["draft_id"],
    })
    a = Approval.model_validate(decision)
    ev = trace_event("approval", "human_decision", decision=a.decision, reason=a.reason, user=a.user)
    if a.decision == "approve":
        return {"approval": {**a.model_dump(), "draft_id": draft_res["draft_id"], "preview": preview}, "preview": preview,
                "status": "approved", "trace": ev}
    if a.decision == "reject":
        return {"approval": a.model_dump(), "status": "rejected", "trace": ev}
    # edit: diff -> style-memory observation -> back through Compliance
    promoted = observe_edit(store, state.get("user_id", "demo"), d["cover_letter"], a.edited_text or "", thread_id)
    return {"approval": a.model_dump(), "draft": {**d, "cover_letter": d["cover_letter"]}, "status": "edited",
            "trace": ev + trace_event("approval", "style_memory", promoted=promoted)}


@node("submit", timeout=60)
async def submit(state: dict, cfg: dict, store) -> dict:
    port = cfg_val(cfg, "port")
    thread_id = cfg["configurable"]["thread_id"]
    ap = state["approval"]
    key = idem_key(thread_id, ap["draft_id"], "submit")
    try:
        res = await port.submit(ap["draft_id"], key)
    except ServerUnavailable as e:
        # leave status=approved so the worker retries this node later with the SAME key
        return {"status": "approved", "error": f"queued: marketplace unavailable ({e.detail})", "trace": trace_event("submit", "degraded", error=str(e))}
    return {"submission": res, "status": "submitted", "error": "",
            "trace": trace_event("submit", "tool_result", tool="marketplace.submit_proposal", proposal_id=res.get("id"),
                                 replay=res.get("idempotent_replay"), connects=res.get("connects_cost"))}
