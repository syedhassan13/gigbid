"""App database (users, inbox, runs, run events, encrypted OAuth tokens). Postgres when
DATABASE_URL is set, SQLite locally. Every query is scoped by user_id (tenant isolation)."""
from __future__ import annotations

import json
import os
import time

from sqlalchemy import (JSON, Column, Float, Integer, MetaData, String, Table, Text, create_engine, insert, select, update)

from agent.settings import HOME

metadata = MetaData()

users = Table("users", metadata,
              Column("id", String, primary_key=True), Column("email", String, unique=True, nullable=False),
              Column("password_hash", String, nullable=False), Column("persona", String), Column("settings", JSON, default=dict),
              Column("created", Float, default=time.time))
inbox = Table("inbox", metadata,
              Column("user_id", String, primary_key=True), Column("job_id", String, primary_key=True),
              Column("thread_id", String), Column("title", String), Column("status", String), Column("action", String),
              Column("fit", Float), Column("risk", Float), Column("is_scam", Integer), Column("price", Float), Column("price_unit", String),
              Column("connects", Integer), Column("category", String), Column("posted_at", String), Column("content_hash", String),
              Column("variant", String), Column("proposal_id", String), Column("pipeline", String), Column("reject_reason", Text),
              Column("updated", Float, default=time.time))
runs = Table("runs", metadata,
             Column("thread_id", String, primary_key=True), Column("user_id", String, index=True), Column("kind", String),
             Column("job_id", String), Column("status", String), Column("trace_id", String), Column("usage", JSON, default=dict),
             Column("created", Float, default=time.time), Column("updated", Float, default=time.time))
run_events = Table("run_events", metadata,
                   Column("id", Integer, primary_key=True, autoincrement=True), Column("thread_id", String, index=True),
                   Column("ts", Float), Column("data", JSON))
oauth_tokens = Table("oauth_tokens", metadata,
                     Column("user_id", String, primary_key=True), Column("provider", String, primary_key=True),
                     Column("enc_token", Text), Column("updated", Float))
worker_state = Table("worker_state", metadata, Column("key", String, primary_key=True), Column("value", JSON))


def _url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres"):
        return url.replace("postgresql://", "postgresql+psycopg://").replace("postgres://", "postgresql+psycopg://")
    p = HOME / "var" / "app.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p}"


engine = create_engine(_url(), pool_pre_ping=True, connect_args={"check_same_thread": False} if _url().startswith("sqlite") else {})


def init() -> None:
    metadata.create_all(engine)


def add_event(thread_id: str, data: dict) -> None:
    with engine.begin() as c:
        c.execute(insert(run_events).values(thread_id=thread_id, ts=time.time(), data=json.loads(json.dumps(data, default=str))))


def events_after(thread_id: str, after: int) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(select(run_events).where(run_events.c.thread_id == thread_id, run_events.c.id > after).order_by(run_events.c.id)).fetchall()
    return [{"id": r.id, "ts": r.ts, **r.data} for r in rows]


def upsert_inbox(user_id: str, job_id: str, **vals) -> None:
    vals["updated"] = time.time()
    with engine.begin() as c:
        exists = c.execute(select(inbox.c.job_id).where(inbox.c.user_id == user_id, inbox.c.job_id == job_id)).first()
        if exists:
            c.execute(update(inbox).where(inbox.c.user_id == user_id, inbox.c.job_id == job_id).values(**vals))
        else:
            c.execute(insert(inbox).values(user_id=user_id, job_id=job_id, **vals))


def upsert_run(thread_id: str, **vals) -> None:
    vals["updated"] = time.time()
    with engine.begin() as c:
        if c.execute(select(runs.c.thread_id).where(runs.c.thread_id == thread_id)).first():
            c.execute(update(runs).where(runs.c.thread_id == thread_id).values(**vals))
        else:
            c.execute(insert(runs).values(thread_id=thread_id, created=time.time(), **vals))


def kv_get(key: str, default=None):
    with engine.connect() as c:
        r = c.execute(select(worker_state.c.value).where(worker_state.c.key == key)).first()
    return r[0] if r else default


def kv_set(key: str, value) -> None:
    with engine.begin() as c:
        if c.execute(select(worker_state.c.key).where(worker_state.c.key == key)).first():
            c.execute(update(worker_state).where(worker_state.c.key == key).values(value=value))
        else:
            c.execute(insert(worker_state).values(key=key, value=value))
