"""Client Liaison (Marketplace read, write after approval; Workspace): read new client
messages, classify intent, draft a reply or propose interview slots, keep the pipeline current."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from langgraph.types import interrupt

from agent import llm
from agent.handoffs import Approval, LiaisonIntent
from agent.mcp_client import ServerUnavailable, call_tool
from agent.memory.promotion_rules import observe_edit
from agent.nodes.approval import idem_key
from agent.nodes.base import cfg_val, node, profile_of
from agent.nodes.compliance import enforce
from agent.nodes.risk import INJECTION, OFF_PLATFORM, FREE_WORK, find
from agent.state import trace_event


@node("load_thread")
async def load_thread(state: dict, cfg: dict, store) -> dict:
    port = cfg_val(cfg, "port")
    try:
        res = await port.messages(state["thread_id"])
        job = await call_tool("liaison", "marketplace", "get_job", {"job_id": res["thread"]["job_id"]}, marketplace_token=port.token)
    except ServerUnavailable as e:
        return {"status": "dead_letter", "error": str(e), "trace": trace_event("load_thread", "degraded", error=str(e))}
    return {"messages": res["messages"], "job": job, "status": "drafting",
            "trace": trace_event("load_thread", "tool_result", tool="marketplace.list_messages", n=len(res["messages"]))}


def classify(text: str) -> LiaisonIntent:
    if find(OFF_PLATFORM, text) or find(FREE_WORK, text):
        return LiaisonIntent(intent="scam_signal", confidence=0.9, summary="asks to move off-platform or for free work")
    if re.search(r"(?i)\b(call|interview|meet|chat)\b.*\b(time|times|slot|when|week|thursday|friday)\b|\binterview you\b", text):
        return LiaisonIntent(intent="interview_request", confidence=0.85, summary="wants to schedule a call")
    if re.search(r"(?i)\b(budget|price|rate|flexib|discount|\$\d+)", text):
        return LiaisonIntent(intent="negotiation", confidence=0.8, summary="discusses price")
    if "?" in text:
        return LiaisonIntent(intent="question", confidence=0.7, summary="asks a question")
    return LiaisonIntent(intent="other", confidence=0.4)


@node("classify_intent")
async def classify_intent(state: dict, cfg: dict, store) -> dict:
    last = next((m for m in reversed(state["messages"]) if m["sender"] == "client"), None)
    text = last["text"] if last else ""
    intent = classify(text)
    if intent.confidence < 0.8:
        out = llm.complete_json("router", llm.prompt("liaison_intent"), llm.untrusted("CLIENT MESSAGE", text), LiaisonIntent, max_tokens=200)
        if out:
            intent = out
    injected = bool(find(INJECTION, text))
    return {"intent": {**intent.model_dump(), "injection_detected": injected},
            "trace": trace_event("classify_intent", "observation", intent=intent.intent, injection=injected)}


@node("draft_reply")
async def draft_reply(state: dict, cfg: dict, store) -> dict:
    intent = state["intent"]["intent"]
    persona = state["persona"]
    job = state["job"]
    last = next((m["text"] for m in reversed(state["messages"]) if m["sender"] == "client"), "")
    slots = []
    if intent == "interview_request":
        start = (datetime.fromisoformat(state["messages"][-1]["created_at"]) + timedelta(days=1)).date().isoformat()
        try:
            slots = await call_tool("liaison", "workspace", "free_slots", {"from_date": start, "days": 5, "max_slots": 3}, user=state.get("user_id", ""))
        except ServerUnavailable:
            slots = []
    floor = profile_of(persona)["rate_floor"]
    text = llm.complete_text("liaison", llm.prompt("liaison_reply", intent=intent, floor=floor, slots=slots),
                             llm.untrusted("CLIENT MESSAGE", last) + f"\n\nJOB: {job['title']}", max_tokens=500)
    if not text:
        if intent == "scam_signal":
            text = ("Thanks for the message. I keep all communication and payments on the platform, and I don't do unpaid test work, "
                    "so I'd be glad to continue here once a contract is in place.")
        elif intent == "interview_request":
            opts = "; ".join(f"{s['start'].replace('T', ' ')}" for s in slots) or "any weekday afternoon"
            text = f"Thanks - happy to talk about {job['title']}. I'm free at: {opts} (your time zone works for me). Which suits you best?"
        elif intent == "negotiation":
            m = re.search(r"\$(\d+)", last)
            ask = float(m.group(1)) if m else None
            if ask is not None and ask < floor and job.get("budget_type") == "hourly":
                text = (f"Thanks for being upfront. I can't go below ${floor}/hour for this scope, but I can reduce the scope of the first "
                        f"milestone to fit your budget. Would that work?")
            else:
                text = ("Thanks - there is some flexibility if we agree a clear first milestone. I can adjust the timeline "
                        "or phase the scope so the first milestone fits your budget. Which matters more to you, speed or scope?")
        else:
            text = (f"Good question. For {job['title']} I'd start by confirming the data and success criteria with you in a short call, "
                    "then deliver a first working milestone for review. Would you like me to outline the milestones in more detail?")
    return {"draft": {"text": text, "intent": intent}, "slots": slots,
            "trace": trace_event("draft_reply", "draft", intent=intent, slots=len(slots))}


@node("liaison_compliance")
async def liaison_compliance(state: dict, cfg: dict, store) -> dict:
    src = state["approval"]["edited_text"] if (state.get("approval") or {}).get("decision") == "edit" else state["draft"]["text"]
    v = enforce(src)
    v_len_ok = v.allowed or (v.blocked_reason or "").startswith("draft too short")  # short replies are fine
    return {"draft": {**state["draft"], "text": v.text}, "compliance": {**v.model_dump(), "allowed": v_len_ok}, "approval": {},
            "status": "awaiting_approval" if v_len_ok else "needs_attention", "error": "" if v_len_ok else (v.blocked_reason or ""),
            "trace": trace_event("liaison_compliance", "verdict", allowed=v_len_ok, fixes=v.fixes_applied)}


@node("liaison_approval", timeout=86400 * 30)
async def liaison_approval(state: dict, cfg: dict, store) -> dict:
    port = cfg_val(cfg, "port")
    key = idem_key(cfg["configurable"]["thread_id"], state["draft"]["text"], "msg")
    try:
        preview = await port.send_message(state["thread_id"], state["draft"]["text"], key, dry_run=True)
    except ServerUnavailable as e:
        return {"status": "dead_letter", "error": str(e)}
    decision = interrupt({"type": "message_approval", "thread_id": state["thread_id"], "messages": state["messages"][-6:],
                          "intent": state["intent"], "draft": state["draft"], "slots": state.get("slots", []),
                          "compliance": state.get("compliance", {}), "dry_run": preview})
    a = Approval.model_validate(decision)
    ev = trace_event("liaison_approval", "human_decision", decision=a.decision, reason=a.reason)
    if a.decision == "edit":
        observe_edit(store, state.get("user_id", "demo"), state["draft"]["text"], a.edited_text or "", cfg["configurable"]["thread_id"])
    return {"approval": a.model_dump(), "status": {"approve": "approved", "reject": "rejected", "edit": "edited"}[a.decision], "trace": ev}


@node("send_reply")
async def send_reply(state: dict, cfg: dict, store) -> dict:
    port = cfg_val(cfg, "port")
    text = state["draft"]["text"]
    key = idem_key(cfg["configurable"]["thread_id"], text, "msg")
    try:
        res = await port.send_message(state["thread_id"], text, key)
        holds = []
        if state["intent"]["intent"] == "interview_request":
            for s in state.get("slots", [])[:3]:
                holds.append(await call_tool("liaison", "workspace", "create_tentative_hold",
                                             {"start": s["start"], "duration_minutes": 30, "title": f"Interview: {state['job']['title'][:60]}",
                                              "idempotency_key": idem_key(key, s["start"], "hold")}, user=state.get("user_id", "")))
    except ServerUnavailable as e:
        return {"status": "approved", "error": f"queued: {e.detail}"}
    return {"sent": {**res, "holds": holds}, "status": "sent", "trace": trace_event("send_reply", "tool_result", tool="marketplace.send_message", replay=res.get("idempotent_replay"))}
