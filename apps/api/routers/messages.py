from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user
from worker import tasks

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/threads", response_model=list[dict])
async def threads(user: dict = Depends(current_user)):
    try:
        res = await tasks.port_for(user).threads()
    except Exception as e:
        raise HTTPException(503, f"marketplace unavailable: {e}")
    with db.engine.connect() as c:
        runs = {r.thread_id: r.status for r in c.execute(select(db.runs).where(db.runs.c.user_id == user["id"], db.runs.c.kind == "conv"))}
    out = []
    for t in res.get("threads", []):
        mine = {k: v for k, v in runs.items() if k.startswith(f"conv:{user['id']}:{t['id']}:")}
        latest = max(mine, key=lambda k: int(k.rsplit(":", 1)[1])) if mine else None
        out.append({**t, "run_thread_id": latest, "run_status": mine.get(latest) if latest else None})
    return out


@router.get("/threads/{thread_id}", response_model=dict)
async def thread(thread_id: str, user: dict = Depends(current_user)):
    try:
        res = await tasks.port_for(user).messages(thread_id)
    except Exception as e:
        raise HTTPException(503, f"marketplace unavailable: {e}")
    return res


@router.post("/threads/{thread_id}/draft", response_model=dict)
async def draft(thread_id: str, user: dict = Depends(current_user)):
    """Ask the Client Liaison to draft a reply now (normally triggered by the pipeline sync)."""
    import asyncio
    asyncio.create_task(tasks.start_conversation(user["id"], thread_id))
    return {"queued": True}
