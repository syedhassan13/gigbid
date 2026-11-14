"""GigBid API (FastAPI). Serves the React build too, so one container can run the whole app.

    uvicorn apps.api.main:app --port 8000
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from agent import llm
from agent.mcp_client import server_status
from agent.settings import ROOT, config
from agent.tracing import current_trace_id, mask_pii
from apps.api import db
from apps.api.auth.security import create_user, current_user
from apps.api.dispatch import worker_mode
from apps.api.routers import analytics, approvals, auth, jobs, messages, runs, settings
from apps.api.schemas import Health
from apps.api.streaming import router as stream_router
from worker import tasks

log = logging.getLogger("gigbid.api")


class PIIFilter(logging.Filter):
    def filter(self, record):
        record.msg = mask_pii(str(record.msg))
        return True


logging.getLogger().addFilter(PIIFilter())


def seed_reviewer() -> None:
    """Reviewer login preloaded with a persona. Credentials come from env (never committed)."""
    email, pw = os.getenv("REVIEWER_EMAIL"), os.getenv("REVIEWER_PASSWORD")
    if not email or not pw:
        return
    with db.engine.connect() as c:
        if c.execute(select(db.users.c.id).where(db.users.c.email == email.lower())).first():
            return
    from mcp_servers.common import write_account
    token = "mcp-reviewer-" + uuid.uuid4().hex[:16]
    write_account(token, {"user": "pending", "adapter": "gigsim", "gigsim_token": os.getenv("GIGSIM_TOKEN_AI_ML", "gs-ai-ml-dev-token")})
    uid = create_user(email, pw, persona="ai_ml", settings={"marketplace": "gigsim", "marketplace_token": token, "rate_floor": 45,
                                                            "target_rate": 65, "weekly_connects_budget": 120, "autonomy": "suggest"})
    write_account(token, {"user": uid, "adapter": "gigsim", "gigsim_token": os.getenv("GIGSIM_TOKEN_AI_ML", "gs-ai-ml-dev-token")})


async def embedded_worker():
    """Scheduler when no Redis: pipeline sync every minute, scouting per config interval."""
    last_scout = 0.0
    interval = config()["scout"]["interval_minutes"] * 60
    while True:
        try:
            await tasks.tick_all()
            if time.time() - last_scout > interval and os.getenv("GIGBID_AUTOSCOUT", "1") == "1":
                last_scout = time.time()
                with db.engine.connect() as c:
                    uids = [r[0] for r in c.execute(select(db.users.c.id).where(db.users.c.persona.is_not(None)))]
                for uid in uids:
                    await tasks.scout_user(uid, max_new=int(os.getenv("GIGBID_SCOUT_MAX", "5")))
        except Exception as e:
            log.warning("embedded worker tick failed: %s", e)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_app):
    db.init()
    seed_reviewer()
    await tasks.runtime()
    # warm the portfolio indexes (embeddings are cached on disk) so the first analysis is not slow
    from rag.retriever import retrieve
    warm = asyncio.gather(*[asyncio.to_thread(retrieve, "python api", p, 3, v) for p in ("ai_ml", "fullstack", "data_analyst")
                            for v in ("v_best", "v2_hybrid")], return_exceptions=True)
    await warm
    bg = asyncio.create_task(embedded_worker()) if worker_mode() == "embedded" else None
    yield
    if bg:
        bg.cancel()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)


@app.middleware("http")
async def trace_id_mw(request: Request, call_next):
    """One trace id flows UI -> API -> graph -> MCP servers -> audit log."""
    tid = request.headers.get("x-trace-id") or uuid.uuid4().hex
    current_trace_id.set(tid)
    resp = await call_next(request)
    resp.headers["x-trace-id"] = tid
    return resp


for r in (auth.router, jobs.router, approvals.router, messages.router, runs.router, analytics.router, settings.router, stream_router):
    app.include_router(r, prefix="/api")

_health_cache: dict = {"t": 0.0, "v": None}


@app.get("/api/health", response_model=Health, tags=["health"])
async def health():
    if time.time() - _health_cache["t"] < 10 and _health_cache["v"]:
        return _health_cache["v"]
    mp = "up"
    try:
        from agent.marketplace_port import MarketplacePort
        await asyncio.wait_for(MarketplacePort(token="mcp-dev-ai_ml").connects(agent="pricing"), 8)
    except Exception:
        mp = "down"
    v = Health(marketplace=mp, mcp=server_status(), llm_profile=config()["profile"], llm_available=llm.available(), worker=worker_mode())
    _health_cache.update(t=time.time(), v=v)
    return v


@app.get("/api/pipeline", response_model=dict, tags=["pipeline"])
def pipeline(user: dict = Depends(current_user)):
    cols = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
    with db.engine.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(select(db.inbox).where(db.inbox.c.user_id == user["id"], db.inbox.c.pipeline.is_not(None)))]
    return {col: [{k: r[k] for k in ("job_id", "title", "price", "price_unit", "variant", "proposal_id", "thread_id", "category")}
                  for r in rows if r["pipeline"] == col] for col in cols}


WEB = Path(os.getenv("WEB_DIST", ROOT / "apps" / "web" / "dist"))
if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB / path
        return FileResponse(f if path and f.is_file() else WEB / "index.html")
