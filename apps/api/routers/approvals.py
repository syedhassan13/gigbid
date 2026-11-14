"""Approvals resume the interrupted LangGraph thread. Pending approvals live in the
checkpointer, so a page refresh (or an API restart) never loses one."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user
from apps.api.dispatch import dispatch
from apps.api.schemas import Decision, Pending, RunStarted
from worker import tasks

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[Pending])
async def pending(user: dict = Depends(current_user)):
    rt = await tasks.runtime()
    with db.engine.connect() as c:
        rows = c.execute(select(db.runs).where(db.runs.c.user_id == user["id"], db.runs.c.status == "awaiting_approval")).fetchall()
    out = []
    for r in rows:
        st = await rt.state(r.kind, r.thread_id)
        if st["interrupts"]:
            p = st["interrupts"][0]
            out.append(Pending(thread_id=r.thread_id, kind=r.kind, title=(p.get("job") or {}).get("title") or p.get("thread_id"), payload=p))
    return out


@router.post("/{thread_id}", response_model=RunStarted)
async def decide(thread_id: str, body: Decision, user: dict = Depends(current_user)):
    if f":{user['id']}:" not in thread_id:
        raise HTTPException(403, "not your thread")
    if body.decision == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edited_text required for edit")
    if body.decision == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    kind = "bid" if thread_id.startswith("bid:") else "conv"
    st = await (await tasks.runtime()).state(kind, thread_id)
    if not st["interrupts"]:
        raise HTTPException(409, "nothing awaiting approval on this thread")
    db.upsert_run(thread_id, status="resuming")
    await dispatch("job_resume_bid" if kind == "bid" else "job_resume_conv", user["id"], thread_id, body.model_dump())
    return RunStarted(thread_id=thread_id)
