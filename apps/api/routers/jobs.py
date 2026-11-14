from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user
from apps.api.dispatch import dispatch
from apps.api.schemas import InboxItem, JobDetail, RunStarted
from worker import tasks

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[InboxItem])
def inbox(filter: str = "all", user: dict = Depends(current_user)):
    with db.engine.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(select(db.inbox).where(db.inbox.c.user_id == user["id"]))]
    if filter == "bid":
        rows = [r for r in rows if r["action"] == "bid"]
    elif filter == "skip":
        rows = [r for r in rows if r["action"] == "skip"]
    elif filter == "open":
        rows = [r for r in rows if r["status"] in ("awaiting_approval", "analysing", "queued", "watch")]
    hidden_auto = (user.get("settings") or {}).get("autonomy") == "auto_skip_low_fit"
    if hidden_auto and filter == "all":
        rows = [r for r in rows if r["action"] != "skip"]
    rows.sort(key=lambda r: (r["is_scam"] or 0, -(r["fit"] or 0), r["posted_at"] or ""), reverse=False)
    return [InboxItem(**{k: r.get(k) for k in InboxItem.model_fields}) for r in rows]


@router.post("/scout", response_model=dict)
async def scout_now(user: dict = Depends(current_user)):
    if not user.get("persona"):
        raise HTTPException(400, "finish onboarding first")
    await dispatch("job_scout", user["id"])
    return {"queued": True}


@router.post("/{job_id}/analyse", response_model=RunStarted)
async def analyse(job_id: str, force_bid: bool = False, user: dict = Depends(current_user)):
    await dispatch("job_analyse", user["id"], job_id, force_bid)
    return RunStarted(thread_id=tasks.bid_thread(user["id"], job_id) + (":force" if force_bid else ""))


@router.get("/{job_id}", response_model=JobDetail)
async def job_detail(job_id: str, user: dict = Depends(current_user)):
    with db.engine.connect() as c:
        row = c.execute(select(db.inbox).where(db.inbox.c.user_id == user["id"], db.inbox.c.job_id == job_id)).first()
    tid = (row.thread_id if row and row.thread_id else tasks.bid_thread(user["id"], job_id))
    rt = await tasks.runtime()
    st = await rt.state("bid", tid)
    v = st["values"]
    if not v:
        try:
            job = await tasks.port_for(user).get_job(job_id)
        except Exception as e:
            raise HTTPException(503, f"marketplace unavailable: {e}")
        return JobDetail(job=job, status=row.status if row else None)
    return JobDetail(job=v.get("job", {}), client=v.get("client", {}), status=v.get("status"), analyses=v.get("analyses", {}),
                     decision=v.get("decision", {}), price=v.get("price", {}), draft=v.get("draft", {}), verification=v.get("verification", {}),
                     critiques=v.get("critiques", []), compliance=v.get("compliance", {}), interrupt=(st["interrupts"] or [None])[0],
                     thread_id=tid, error=v.get("error"))
