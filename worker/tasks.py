"""Background work (E1): scouting, bid runs, resumes, pipeline sync, conversation drafts.
Runs in the Arq worker (Redis) or, without Redis, in the API's embedded worker loop -
never inside a web request. Every task is idempotent: thread ids are deterministic
(bid:<user>:<job>), a running/finished thread is never re-analysed, and submits carry
idempotency keys, so a worker restart never double-analyses or double-submits."""
from __future__ import annotations

import asyncio
import logging
import time

from langgraph.types import Command
from sqlalchemy import select

from agent.marketplace_port import MarketplacePort
from agent.memory.promotion_rules import observe_outcome
from agent.mcp_client import ServerUnavailable
from agent.nodes.scout import scout_saved_searches
from apps.api import db

log = logging.getLogger("gigbid.worker")
_RT = None
_running: set[str] = set()


async def runtime():
    global _RT
    if _RT is None:
        from agent.runtime import Runtime
        _RT = await Runtime().start()
    return _RT


def get_user(user_id: str) -> dict:
    with db.engine.connect() as c:
        return dict(c.execute(select(db.users).where(db.users.c.id == user_id)).first()._mapping)


def port_for(user: dict) -> MarketplacePort:
    s = user.get("settings") or {}
    return MarketplacePort(token=s.get("marketplace_token") or f"mcp-dev-{user['persona']}", user=user["id"])


def bid_thread(user_id: str, job_id: str) -> str:
    return f"bid:{user_id}:{job_id}"


async def _drive(kind: str, thread_id: str, inp, user: dict, job_id: str | None = None) -> dict:
    rt = await runtime()
    prefs = {k: v for k, v in (user.get("settings") or {}).items() if k in ("rate_floor", "target_rate")}
    final = {}
    db.upsert_run(thread_id, user_id=user["id"], kind=kind, job_id=job_id, status="running")
    async for ev in rt.stream(kind, thread_id, inp, port_for(user), user["persona"], user_prefs=prefs):
        db.add_event(thread_id, ev)
        if ev["type"] == "done":
            final = ev
            db.upsert_run(thread_id, status=ev["status"] or "done", trace_id=ev.get("trace_id"), usage=ev.get("usage"))
    if kind == "bid" and job_id:
        await _sync_inbox(user, job_id, thread_id)
    return final


async def _sync_inbox(user: dict, job_id: str, thread_id: str) -> None:
    st = (await (await runtime()).state("bid", thread_id))["values"]
    a = st.get("analyses", {})
    job = st.get("job", {})
    db.upsert_inbox(user["id"], job_id, thread_id=thread_id, title=job.get("title"), status=st.get("status"),
                    action=(st.get("decision") or {}).get("action"), fit=(a.get("fit") or {}).get("fit_score"),
                    risk=(a.get("risk") or {}).get("risk_score"), is_scam=int(bool((a.get("risk") or {}).get("is_scam"))),
                    price=(st.get("price") or {}).get("amount"), price_unit=(st.get("price") or {}).get("unit"),
                    connects=job.get("connects_cost"), category=job.get("category"), posted_at=job.get("posted_at"),
                    variant=(st.get("draft") or {}).get("variant"), proposal_id=(st.get("submission") or {}).get("id"),
                    pipeline="submitted" if st.get("status") == "submitted" else ("drafted" if st.get("status") == "awaiting_approval" else None),
                    reject_reason=(st.get("approval") or {}).get("reason") if st.get("status") == "rejected" else None)


async def analyse_job(user_id: str, job_id: str, force_bid: bool = False) -> dict:
    user = get_user(user_id)
    tid = bid_thread(user_id, job_id) + (":force" if force_bid else "")
    if tid in _running:
        return {"status": "already_running", "thread_id": tid}
    rt = await runtime()
    existing = await rt.state("bid", tid)
    if existing["values"] and not existing["next"] and existing["values"].get("status") not in ("dead_letter", None):
        return {"status": existing["values"].get("status"), "thread_id": tid, "cached": True}  # idempotent: never re-analyse
    _running.add(tid)
    try:
        inp = None if existing["next"] else {"job_id": job_id, "persona": user["persona"], "user_id": user_id,
                                             "autonomy": (user.get("settings") or {}).get("autonomy", "suggest"), "force_bid": force_bid}
        db.upsert_inbox(user_id, job_id, thread_id=tid, status="analysing")
        return await _drive("bid", tid, inp, user, job_id)
    finally:
        _running.discard(tid)


async def resume_bid(user_id: str, thread_id: str, decision: dict) -> dict:
    user = get_user(user_id)
    job_id = thread_id.split(":")[2]
    return await _drive("bid", thread_id, Command(resume={**decision, "user": user_id}), user, job_id)


async def scout_user(user_id: str, max_new: int = 8) -> dict:
    """Saved searches -> dedup against everything already in the inbox -> analyse new jobs."""
    user = get_user(user_id)
    with db.engine.connect() as c:
        seen = {r[0] for r in c.execute(select(db.inbox.c.content_hash).where(db.inbox.c.user_id == user_id)) if r[0]}
    last = db.kv_get(f"scout_after:{user_id}")
    try:
        jobs = await scout_saved_searches(port_for(user), user["persona"], seen, posted_after=last)
    except ServerUnavailable as e:
        db.kv_set(f"marketplace_down:{user_id}", time.time())
        return {"status": "degraded", "error": str(e)}
    jobs.sort(key=lambda j: j["posted_at"])
    for j in jobs:
        db.upsert_inbox(user_id, j["id"], title=j["title"], status="queued", content_hash=j["content_hash"], posted_at=j["posted_at"],
                        connects=j.get("connects_cost"), category=j.get("category"))
    if jobs:
        db.kv_set(f"scout_after:{user_id}", max(j["posted_at"] for j in jobs))
    for j in jobs[:max_new]:
        await analyse_job(user_id, j["id"])
    return {"status": "ok", "new_jobs": len(jobs), "analysed": min(len(jobs), max_new)}


async def sync_pipeline(user_id: str) -> dict:
    """Marketplace events -> pipeline board + outcome memory; client replies -> conversation drafts."""
    user = get_user(user_id)
    port = port_for(user)
    after = db.kv_get(f"events_after:{user_id}", 0)
    try:
        evs = (await port.events(after)).get("events", [])
    except ServerUnavailable as e:
        return {"status": "degraded", "error": str(e)}
    rt = await runtime()
    with db.engine.connect() as c:
        by_prop = {r.proposal_id: dict(r._mapping) for r in c.execute(select(db.inbox).where(db.inbox.c.user_id == user_id)) if r.proposal_id}
    started = 0
    for e in evs:
        p = e["payload"]
        row = by_prop.get(p.get("proposal_id"))
        if e["type"] == "proposal_status" and row:
            db.upsert_inbox(user_id, row["job_id"], pipeline=p["status"])
            observe_outcome(rt.store, user_id, p["proposal_id"], row.get("category") or "other", row.get("variant"), p["status"])
        if e["type"] == "client_replied":
            if row:
                db.upsert_inbox(user_id, row["job_id"], pipeline="replied")
            await start_conversation(user_id, p["thread_id"])
            started += 1
        after = max(after, e["seq"])
    db.kv_set(f"events_after:{user_id}", after)
    return {"status": "ok", "events": len(evs), "conversations": started}


def conv_thread(user_id: str, mp_thread: str, n_messages: int | None = None) -> str:
    return f"conv:{user_id}:{mp_thread}" + (f":{n_messages}" if n_messages is not None else "")


async def start_conversation(user_id: str, mp_thread: str) -> dict:
    user = get_user(user_id)
    msgs = (await port_for(user).messages(mp_thread))["messages"]
    tid = conv_thread(user_id, mp_thread, len(msgs))  # one run per new client message
    rt = await runtime()
    if (await rt.state("conv", tid))["values"]:
        return {"status": "exists", "thread_id": tid}
    return await _drive("conv", tid, {"thread_id": mp_thread, "persona": user["persona"], "user_id": user_id}, user)


async def resume_conversation(user_id: str, thread_id: str, decision: dict) -> dict:
    return await _drive("conv", thread_id, Command(resume={**decision, "user": user_id}), get_user(user_id))


async def retry_queued(user_id: str) -> int:
    """Recover after an outage: resume threads left 'approved' (submit queued) or dead-lettered."""
    rt = await runtime()
    n = 0
    with db.engine.connect() as c:
        rows = c.execute(select(db.runs).where(db.runs.c.user_id == user_id, db.runs.c.status.in_(["approved", "dead_letter"]))).fetchall()
    for r in rows:
        st = await rt.state(r.kind, r.thread_id)
        if st["values"].get("status") == "approved" and not st["next"] and (r.kind == "conv" or (st["values"].get("approval") or {}).get("draft_id")):
            # re-enter after the approval node -> router sends it to submit; same idempotency key => exactly once
            await rt.graph(r.kind).aupdate_state({"configurable": {"thread_id": r.thread_id}}, {"status": "approved"},
                                                    as_node="approval" if r.kind == "bid" else "liaison_approval")
            await _drive(r.kind, r.thread_id, None, get_user(user_id), r.job_id)
            n += 1
        elif st["values"].get("status") == "dead_letter" and r.kind == "bid" and r.job_id:
            await analyse_job(user_id, r.job_id)
            n += 1
    return n


async def tick_all() -> None:
    """One scheduler tick for every onboarded user."""
    with db.engine.connect() as c:
        uids = [r[0] for r in c.execute(select(db.users.c.id).where(db.users.c.persona.is_not(None)))]
    for uid in uids:
        try:
            await sync_pipeline(uid)
            await retry_queued(uid)
        except Exception as e:  # never kill the loop
            log.warning("tick failed for %s: %s", uid, e)
    await asyncio.sleep(0)
