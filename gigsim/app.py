"""GigSim: a safe, repeatable marketplace simulator (REST API + seed data).

Built for this assignment because no starter kit was provided. GigBid never
calls it directly - only through the Marketplace MCP server's GigSim adapter.

Run:  uvicorn gigsim.app:app --port 8100
Env:  GIGSIM_DB (sqlite path), GIGSIM_ERROR_RATE (0.02), GIGSIM_RATE_LIMIT (per token / minute, 120),
      GIGSIM_POLICY_VERSION (default latest), GIGSIM_AUTOTICK_SECONDS (0 = off)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sqlite3
import statistics
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gigsim import client_sim
from gigsim.generator import connects_cost

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("GIGSIM_DB", ROOT / "var" / "gigsim.db"))
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.02"))
RATE_LIMIT = int(os.getenv("GIGSIM_RATE_LIMIT", "120"))
SIM_START = datetime(2026, 11, 1)

FREELANCERS = {  # demo accounts; tokens are simulator-only secrets (override with env in deployment)
    "f-ai_ml": {"persona": "ai_ml", "token": os.getenv("GIGSIM_TOKEN_AI_ML", "gs-ai-ml-dev-token")},
    "f-fullstack": {"persona": "fullstack", "token": os.getenv("GIGSIM_TOKEN_FULLSTACK", "gs-fullstack-dev-token")},
    "f-data_analyst": {"persona": "data_analyst", "token": os.getenv("GIGSIM_TOKEN_DATA_ANALYST", "gs-data-analyst-dev-token")},
}

_lock = threading.RLock()


def policy() -> dict:
    vs = yaml.safe_load((ROOT / "gigsim" / "policy_versions.yaml").read_text())["versions"]
    v = int(os.getenv("GIGSIM_POLICY_VERSION", max(vs)))
    return {"version": v, **vs[v]}


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT, kind TEXT, posted_at TEXT, category TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS freelancers(id TEXT PRIMARY KEY, persona TEXT, token TEXT UNIQUE, connects INTEGER);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, freelancer_id TEXT, job_id TEXT, idem_key TEXT UNIQUE, data TEXT,
  status TEXT, created_at TEXT, decision TEXT, variant TEXT);
CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY, freelancer_id TEXT, client_id TEXT, job_id TEXT, proposal_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, thread_id TEXT, sender TEXT, text TEXT, created_at TEXT, idem_key TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, freelancer_id TEXT, type TEXT, payload TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_jobs_posted ON jobs(posted_at);
"""


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def seed(reset: bool = False) -> dict:
    with _lock:
        c = db()
        if reset:
            for t in ("meta", "jobs", "clients", "freelancers", "proposals", "threads", "messages", "events"):
                c.execute(f"DROP TABLE IF EXISTS {t}")
        c.executescript(SCHEMA)
        if c.execute("SELECT v FROM meta WHERE k='seeded'").fetchone():
            return {"seeded": False}
        proc, dev = ROOT / "data" / "processed", ROOT / "evals" / "datasets"
        jobs = [(j, "historical", "closed") for j in _jsonl(proc / "historical_jobs.jsonl")]
        for p in ("ai_ml", "fullstack", "data_analyst"):
            jobs += [(j, "dev", "open") for j in _jsonl(dev / f"dev_{p}.jsonl")]
        jobs += [(j, "stream", "open") for j in _jsonl(proc / "stream_jobs.jsonl")]
        hidden_path = Path(os.getenv("GIGSIM_HIDDEN_SET", "/nonexistent"))
        jobs += [(j, "hidden", "open") for j in _jsonl(hidden_path)]
        for j, kind, st in jobs:
            c.execute("INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?)", (j["id"], json.dumps(j), kind, j["posted_at"], j["category"], st))
        for cl in _jsonl(proc / "clients.jsonl") + _jsonl(dev / "dev_clients.jsonl"):
            c.execute("INSERT OR IGNORE INTO clients VALUES (?,?)", (cl["id"], json.dumps(cl)))
        for fid, f in FREELANCERS.items():
            c.execute("INSERT OR REPLACE INTO freelancers VALUES (?,?,?,?)", (fid, f["persona"], f["token"], policy()["weekly_free_connects"] * 10))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('seeded','1')")
        c.execute("INSERT OR REPLACE INTO meta VALUES ('now',?)", (SIM_START.isoformat(),))
        c.commit()
        return {"seeded": True, "jobs": len(jobs)}


def sim_now(c) -> datetime:
    r = c.execute("SELECT v FROM meta WHERE k='now'").fetchone()
    return datetime.fromisoformat(r["v"]) if r else SIM_START


# ---------------------------------------------------------------- auth / limits / chaos
_hits: dict[str, deque] = defaultdict(deque)


def auth(request: Request, authorization: str = Header(default="")) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    c = db()
    row = c.execute("SELECT * FROM freelancers WHERE token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    now = time.time()
    q = _hits[token]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
    q.append(now)
    if request.method == "GET" and random.random() < ERROR_RATE:
        raise HTTPException(503, "transient upstream error (simulated)")
    return dict(row)


def public_job(j: dict) -> dict:
    return {k: v for k, v in j.items() if k not in ("gold",)}


def public_client(cl: dict) -> dict:
    return {k: v for k, v in cl.items() if k != "hidden"}


# ---------------------------------------------------------------- simulation tick
def tick(minutes: int = 60) -> dict:
    """Advance the clock: release stream jobs, let clients react to proposals."""
    with _lock:
        c = db()
        now = sim_now(c) + timedelta(minutes=minutes)
        c.execute("UPDATE meta SET v=? WHERE k='now'", (now.isoformat(),))
        n_events = 0
        for p in c.execute("SELECT * FROM proposals WHERE status IN ('submitted','viewed','replied')").fetchall():
            data = json.loads(p["data"])
            created = datetime.fromisoformat(p["created_at"])
            age_h = (now - created).total_seconds() / 3600
            job = json.loads(c.execute("SELECT data FROM jobs WHERE id=?", (p["job_id"],)).fetchone()["data"])
            client = json.loads(c.execute("SELECT data FROM clients WHERE id=?", (job["client_id"],)).fetchone()["data"])
            dec = json.loads(p["decision"]) if p["decision"] else client_sim.decide(p["id"], job, client, data["cover_letter"], data["bid_amount"])
            status = p["status"]
            if status == "submitted" and age_h >= 2:
                status = "viewed"
            if status == "viewed" and age_h >= 6:
                if dec["replied"]:
                    status = "replied"
                    tid = "t-" + p["id"][2:]
                    c.execute("INSERT OR IGNORE INTO threads VALUES (?,?,?,?,?,?)", (tid, p["freelancer_id"], job["client_id"], job["id"], p["id"], now.isoformat()))
                    kind = "scam" if dec.get("scam") else ("interview" if dec["interview"] else random.Random(p["id"]).choice(["question", "negotiation"]))
                    c.execute("INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?)", ("m-" + hashlib.sha1((tid + "1").encode()).hexdigest()[:10], tid, "client",
                              client_sim.client_message(kind, job, data["bid_amount"], p["id"]), now.isoformat(), None))
                    _event(c, p["freelancer_id"], "client_replied", {"proposal_id": p["id"], "thread_id": tid, "kind": kind}, now)
                elif age_h >= 72:
                    status = "lost"
            if status == "replied" and age_h >= 30 and dec["replied"]:
                fl_msgs = c.execute("SELECT COUNT(*) n FROM messages m JOIN threads t ON m.thread_id=t.id WHERE t.proposal_id=? AND m.sender='freelancer'", (p["id"],)).fetchone()["n"]
                if fl_msgs:
                    status = "interview" if dec["interview"] else "lost"
            if status != p["status"]:
                n_events += 1
                c.execute("UPDATE proposals SET status=?, decision=? WHERE id=?", (status, json.dumps(dec), p["id"]))
                _event(c, p["freelancer_id"], "proposal_status", {"proposal_id": p["id"], "status": status}, now)
        for p in c.execute("SELECT * FROM proposals WHERE status='interview'").fetchall():
            if (now - datetime.fromisoformat(p["created_at"])).total_seconds() / 3600 >= 54:
                dec = json.loads(p["decision"])
                st = "hired" if dec["hired"] else "lost"
                c.execute("UPDATE proposals SET status=? WHERE id=?", (st, p["id"]))
                _event(c, p["freelancer_id"], "proposal_status", {"proposal_id": p["id"], "status": st}, now)
        c.commit()
        return {"now": now.isoformat(), "events": n_events}


def _event(c, fid, typ, payload, now):
    c.execute("INSERT INTO events(freelancer_id,type,payload,created_at) VALUES (?,?,?,?)", (fid, typ, json.dumps(payload), now.isoformat()))


@asynccontextmanager
async def lifespan(_app):
    seed()
    task = None
    secs = int(os.getenv("GIGSIM_AUTOTICK_SECONDS", "0"))
    if secs:
        async def loop():
            while True:
                await asyncio.sleep(secs)
                tick(60)
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="GigSim", version="1.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def _http_exc(_req, exc: HTTPException):
    return JSONResponse({"error": exc.detail, "status": exc.status_code}, status_code=exc.status_code, headers=exc.headers)


@app.get("/health")
def health():
    return {"ok": True, "policy_version": policy()["version"]}


@app.get("/v1/policy")
def get_policy(_: dict = Depends(auth)):
    return policy()


@app.get("/v1/jobs")
def search_jobs(q: str = "", category: str | None = None, posted_after: str | None = None, include_dev: bool = False,
                limit: int = 20, offset: int = 0, me: dict = Depends(auth)):
    c = db()
    now = sim_now(c).isoformat()
    kinds = ("stream", "hidden") + (("dev",) if include_dev else ())
    sql = f"SELECT data FROM jobs WHERE status='open' AND kind IN ({','.join('?' * len(kinds))}) AND posted_at<=?"
    args: list = [*kinds, now]
    if category:
        sql += " AND category=?"
        args.append(category)
    if posted_after:
        sql += " AND posted_at>?"
        args.append(posted_after)
    rows = [json.loads(r["data"]) for r in c.execute(sql + " ORDER BY posted_at DESC", args).fetchall()]
    if q:
        terms = [t for t in q.lower().split() if t]
        rows = [j for j in rows if any(t in (j["title"] + " " + j["description"]).lower() for t in terms)]
    return {"now": now, "total": len(rows), "jobs": [public_job(j) for j in rows[offset: offset + min(limit, 100)]]}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, _: dict = Depends(auth)):
    r = db().execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        raise HTTPException(404, "job not found")
    return public_job(json.loads(r["data"]))


@app.get("/v1/clients/{client_id}")
def get_client(client_id: str, _: dict = Depends(auth)):
    r = db().execute("SELECT data FROM clients WHERE id=?", (client_id,)).fetchone()
    if not r:
        raise HTTPException(404, "client not found")
    return public_client(json.loads(r["data"]))


@app.get("/v1/market/stats")
def market_stats(category: str, _: dict = Depends(auth)):
    rows = [json.loads(r["data"]) for r in db().execute("SELECT data FROM jobs WHERE kind='historical' AND category=?", (category,)).fetchall()]
    fixed = sorted(j["budget_max"] for j in rows if j["budget_type"] == "fixed" and j["budget_max"])
    hourly = sorted(j["budget_max"] for j in rows if j["budget_type"] == "hourly" and j["budget_max"])

    def q(xs):
        if len(xs) < 5:
            return None
        qs = statistics.quantiles(xs, n=4)
        return {"n": len(xs), "p25": round(qs[0], 1), "p50": round(qs[1], 1), "p75": round(qs[2], 1)}
    return {"category": category, "fixed": q(fixed), "hourly_high": q(hourly), "sources": sorted({j["source"].split(":")[0] for j in rows})}


@app.get("/v1/me/connects")
def connects(me: dict = Depends(auth)):
    return {"freelancer_id": me["id"], "balance": db().execute("SELECT connects FROM freelancers WHERE id=?", (me["id"],)).fetchone()["connects"]}


class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str = Field(min_length=20)
    bid_amount: float = Field(gt=0)
    screening_answers: list[str] = []
    dry_run: bool = False
    variant: str | None = None  # X2 A/B experiment arm, recorded for analysis


@app.post("/v1/proposals")
def submit_proposal(body: ProposalIn, me: dict = Depends(auth), idempotency_key: str = Header(default="")):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")
    pol = policy()
    with _lock:
        c = db()
        prev = c.execute("SELECT * FROM proposals WHERE idem_key=?", (idempotency_key,)).fetchone()
        if prev:
            return {**json.loads(prev["data"]), "id": prev["id"], "status": prev["status"], "idempotent_replay": True}
        jr = c.execute("SELECT data, status FROM jobs WHERE id=?", (body.job_id,)).fetchone()
        if not jr:
            raise HTTPException(404, "job not found")
        job = json.loads(jr["data"])
        cost = connects_cost(job, pol)
        violations = []
        if len(body.cover_letter) > pol["max_cover_letter_chars"]:
            violations.append(f"cover letter exceeds {pol['max_cover_letter_chars']} chars")
        for phrase in pol.get("required_phrases", []):
            if phrase.lower() not in body.cover_letter.lower():
                violations.append(f"missing required statement: '{phrase}'")
        bal = c.execute("SELECT connects FROM freelancers WHERE id=?", (me["id"],)).fetchone()["connects"]
        preview = {"job_id": body.job_id, "cover_letter": body.cover_letter, "bid_amount": body.bid_amount,
                   "screening_answers": body.screening_answers, "connects_cost": cost, "connects_balance_after": bal - cost,
                   "policy_version": pol["version"], "violations": violations, "variant": body.variant}
        if body.dry_run:
            return {"dry_run": True, **preview}
        if violations:
            raise HTTPException(422, {"violations": violations})
        if bal < cost:
            raise HTTPException(402, "not enough connects")
        if c.execute("SELECT 1 FROM proposals WHERE freelancer_id=? AND job_id=?", (me["id"], body.job_id)).fetchone():
            raise HTTPException(409, "already applied to this job")
        pid = "p-" + hashlib.sha1(idempotency_key.encode()).hexdigest()[:12]
        now = sim_now(c)
        c.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?)", (pid, me["id"], body.job_id, idempotency_key, json.dumps(preview), "submitted", now.isoformat(), None, body.variant))
        c.execute("UPDATE freelancers SET connects=connects-? WHERE id=?", (cost, me["id"]))
        _event(c, me["id"], "proposal_status", {"proposal_id": pid, "status": "submitted"}, now)
        c.commit()
        return {**preview, "id": pid, "status": "submitted", "idempotent_replay": False}


@app.get("/v1/proposals")
def list_proposals(me: dict = Depends(auth)):
    rows = db().execute("SELECT id, job_id, status, created_at, variant, data FROM proposals WHERE freelancer_id=? ORDER BY created_at DESC", (me["id"],)).fetchall()
    return {"proposals": [{"id": r["id"], "job_id": r["job_id"], "status": r["status"], "created_at": r["created_at"], "variant": r["variant"],
                           "bid_amount": json.loads(r["data"])["bid_amount"], "connects_cost": json.loads(r["data"])["connects_cost"]} for r in rows]}


@app.get("/v1/threads")
def list_threads(me: dict = Depends(auth)):
    c = db()
    out = []
    for t in c.execute("SELECT * FROM threads WHERE freelancer_id=? ORDER BY created_at DESC", (me["id"],)).fetchall():
        last = c.execute("SELECT sender, text, created_at FROM messages WHERE thread_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (t["id"],)).fetchone()
        out.append({**dict(t), "last_message": dict(last) if last else None})
    return {"threads": out}


@app.get("/v1/threads/{thread_id}/messages")
def thread_messages(thread_id: str, me: dict = Depends(auth)):
    c = db()
    t = c.execute("SELECT * FROM threads WHERE id=? AND freelancer_id=?", (thread_id, me["id"])).fetchone()
    if not t:
        raise HTTPException(404, "thread not found")
    msgs = [dict(m) for m in c.execute("SELECT id, sender, text, created_at FROM messages WHERE thread_id=? ORDER BY created_at, rowid", (thread_id,)).fetchall()]
    return {"thread": dict(t), "messages": msgs}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    dry_run: bool = False


@app.post("/v1/threads/{thread_id}/messages")
def send_message(thread_id: str, body: MessageIn, me: dict = Depends(auth), idempotency_key: str = Header(default="")):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")
    with _lock:
        c = db()
        if not c.execute("SELECT 1 FROM threads WHERE id=? AND freelancer_id=?", (thread_id, me["id"])).fetchone():
            raise HTTPException(404, "thread not found")
        prev = c.execute("SELECT * FROM messages WHERE idem_key=?", (idempotency_key,)).fetchone()
        if prev:
            return {**dict(prev), "idempotent_replay": True}
        if body.dry_run:
            return {"dry_run": True, "thread_id": thread_id, "text": body.text, "connects_cost": 0}
        mid = "m-" + hashlib.sha1(idempotency_key.encode()).hexdigest()[:10]
        now = sim_now(c)
        c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", (mid, thread_id, "freelancer", body.text, now.isoformat(), idempotency_key))
        c.commit()
        return {"id": mid, "thread_id": thread_id, "sender": "freelancer", "text": body.text, "created_at": now.isoformat(), "idempotent_replay": False}


@app.get("/v1/events")
def events(after: int = 0, me: dict = Depends(auth)):
    rows = db().execute("SELECT * FROM events WHERE freelancer_id=? AND seq>? ORDER BY seq LIMIT 200", (me["id"], after)).fetchall()
    return {"events": [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]}


@app.post("/v1/admin/tick")
def admin_tick(minutes: int = 60, _: dict = Depends(auth)):
    return tick(minutes)


@app.post("/v1/admin/reset")
def admin_reset(_: dict = Depends(auth)):
    return seed(reset=True)
