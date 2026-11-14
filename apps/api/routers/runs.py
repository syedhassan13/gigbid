from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user
from worker import tasks

router = APIRouter(prefix="/runs", tags=["runs"])


def _own(thread_id: str, user: dict) -> str:
    if f":{user['id']}:" not in thread_id:
        raise HTTPException(403, "not your run")
    return "bid" if thread_id.startswith("bid:") else "conv"


@router.get("", response_model=list[dict])
def list_runs(user: dict = Depends(current_user)):
    with db.engine.connect() as c:
        rows = c.execute(select(db.runs).where(db.runs.c.user_id == user["id"]).order_by(db.runs.c.updated.desc()).limit(100)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{thread_id}", response_model=dict)
async def run_detail(thread_id: str, user: dict = Depends(current_user)):
    kind = _own(thread_id, user)
    st = await (await tasks.runtime()).state(kind, thread_id)
    with db.engine.connect() as c:
        r = c.execute(select(db.runs).where(db.runs.c.thread_id == thread_id)).first()
    return {"run": dict(r._mapping) if r else None, "status": st["values"].get("status"), "next": st["next"],
            "trace": st["values"].get("trace", []), "steps": st["values"].get("steps"), "tokens": st["values"].get("tokens"),
            "cost_usd": st["values"].get("cost_usd"), "events": db.events_after(thread_id, 0)[-200:]}


@router.get("/{thread_id}/history", response_model=list[dict])
async def history(thread_id: str, user: dict = Depends(current_user)):
    return await (await tasks.runtime()).history(_own(thread_id, user), thread_id)


@router.post("/{thread_id}/replay/{checkpoint_id}", response_model=dict)
async def replay(thread_id: str, checkpoint_id: str, user: dict = Depends(current_user)):
    kind = _own(thread_id, user)
    st = await (await tasks.runtime()).replay(kind, thread_id, checkpoint_id, tasks.port_for(user), user["persona"])
    return {"status": st["values"].get("status"), "next": st["next"]}
