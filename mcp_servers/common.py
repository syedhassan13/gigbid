"""Shared plumbing for GigBid's HTTP MCP servers: bearer-token auth, per-user
token-bucket rate limiting, append-only audit log with PII masking, trace ids."""
from __future__ import annotations

import contextvars
import json
import os
import threading
import time

from agent.settings import HOME
from agent.tracing import mask_obj

AUDIT_DIR = HOME / "var" / "audit"
_lock = threading.Lock()
# in-process transport has no HTTP headers: the caller sets these before connecting
INPROC_HEADERS: contextvars.ContextVar[dict] = contextvars.ContextVar("INPROC_HEADERS", default={})


class TokenBucket:
    def __init__(self, rate_per_min: float, burst: int):
        self.rate, self.burst = rate_per_min / 60.0, burst
        self.state: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def take(self, key: str) -> float:
        """Returns 0 if allowed, else seconds to wait."""
        with self.lock:
            tokens, ts = self.state.get(key, (self.burst, time.time()))
            now = time.time()
            tokens = min(self.burst, tokens + (now - ts) * self.rate)
            if tokens >= 1:
                self.state[key] = (tokens - 1, now)
                return 0.0
            self.state[key] = (tokens, now)
            return (1 - tokens) / self.rate


def audit(server: str, user: str, tool: str, args: dict, result: object, trace_id: str = "", error: str | None = None) -> None:
    """Append-only JSONL audit log: user, tool, arguments, result, trace id (PII masked)."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    res = mask_obj(result if isinstance(result, (dict, list, int, float, type(None))) else str(result))
    if isinstance(res, str):
        res = res[:4000]
    rec = {"ts": time.time(), "server": server, "user": user, "tool": tool, "args": mask_obj(args),
           "result": res, "trace_id": trace_id, "error": error}
    with _lock, open(AUDIT_DIR / f"{server}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def read_accounts() -> dict:
    """Bearer token -> account mapping, written by the API when a user connects a marketplace account."""
    p = HOME / "var" / "marketplace_accounts.json"
    accounts = json.loads(p.read_text()) if p.exists() else {}
    # dev defaults (simulator only)
    for persona, tok in (("ai_ml", "gs-ai-ml-dev-token"), ("fullstack", "gs-fullstack-dev-token"), ("data_analyst", "gs-data-analyst-dev-token")):
        accounts.setdefault(f"mcp-dev-{persona}", {"user": f"dev-{persona}", "adapter": "gigsim", "gigsim_token": tok})
    return accounts


def write_account(token: str, account: dict) -> None:
    p = HOME / "var" / "marketplace_accounts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        cur = json.loads(p.read_text()) if p.exists() else {}
        cur[token] = account
        p.write_text(json.dumps(cur, indent=2))


def request_headers(ctx) -> dict:
    try:
        req = ctx.request_context.request
        if req is not None:
            return {k.lower(): v for k, v in req.headers.items()}
    except Exception:
        pass
    return {k.lower(): v for k, v in INPROC_HEADERS.get().items()}


def default_token() -> str:
    return os.getenv("MARKETPLACE_DEFAULT_TOKEN", "")

