"""Long-term memory store (LangGraph BaseStore). Postgres in compose/deploy, SQLite locally.
Namespaces (per user):
  ("style", user)              promoted style rules, e.g. {"rule": "cut_first_sentence"}
  ("style_candidates", user)   observations awaiting promotion (never read by the writer)
  ("outcome", user)            promoted outcome stats per job category / experiment arm
  ("outcome_obs", user)        raw outcome observations awaiting promotion
"""
from __future__ import annotations

import os
import sqlite3

from agent.settings import HOME

_store = None


def get_store():
    global _store
    if _store is not None:
        return _store
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres"):
        from langgraph.store.postgres import PostgresStore
        from psycopg import Connection
        conn = Connection.connect(url, autocommit=True, prepare_threshold=0)
        _store = PostgresStore(conn)
    else:
        from langgraph.store.sqlite import SqliteStore
        p = HOME / "var" / "memory.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        _store = SqliteStore(sqlite3.connect(p, check_same_thread=False, isolation_level=None))
    _store.setup()
    return _store


def style_rules(store, user: str) -> list[dict]:
    return [i.value | {"key": i.key} for i in store.search(("style", user), limit=50)] if store else []


def outcome_memory(store, user: str) -> list[dict]:
    return [i.value | {"key": i.key} for i in store.search(("outcome", user), limit=50)] if store else []
