"""SSE bridge: LangGraph stream events are persisted by the worker (run_events) and
streamed here, so a viewer can attach to a run started anywhere (worker, other tab)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from apps.api import db
from apps.api.auth.security import user_from_token

router = APIRouter(tags=["runs"])


def _run_status(thread_id: str) -> str | None:
    from sqlalchemy import select
    with db.engine.connect() as c:
        r = c.execute(select(db.runs.c.status).where(db.runs.c.thread_id == thread_id)).first()
    return r[0] if r else None


@router.get("/runs/{thread_id}/stream")
async def stream(thread_id: str, token: str = Query(...), after: int = 0):
    user = user_from_token(token)  # EventSource cannot set headers -> token in query
    if not user or f":{user['id']}:" not in thread_id:
        raise HTTPException(403, "not your run")

    async def gen():
        last, idle = after, 0
        while idle < 600:
            evs = db.events_after(thread_id, last)
            for e in evs:
                last = e["id"]
                yield {"event": e.get("type", "update"), "id": str(e["id"]), "data": json.dumps(e, default=str)}
            idle = 0 if evs else idle + 1
            if evs and evs[-1].get("type") == "done":
                await asyncio.sleep(1.5)
                if not db.events_after(thread_id, last) and _run_status(thread_id) not in ("running", "resuming"):
                    yield {"event": "end", "data": "{}"}
                    return
            await asyncio.sleep(0.4)
    return EventSourceResponse(gen(), ping=10)
