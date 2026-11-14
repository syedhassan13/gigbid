"""GigBid Marketplace MCP server: one port, two adapters (GigSim | live Upwork).

Read tools: search_jobs, get_job, get_client_history, get_connects_balance, get_market_stats,
            get_policy, list_proposals, list_threads, list_messages, get_events
Write tools: create_proposal_draft, submit_proposal, send_message
  * Pydantic input schemas with real constraints + declared output schemas
  * annotations: readOnlyHint / destructiveHint / idempotentHint
  * idempotency key on every write (stored here; replay returns the stored result)
  * dry_run returns exactly what would be sent and what it costs
Transport: Streamable HTTP with bearer-token auth, per-user rate limiter that stays
under GigSim's limit, append-only audit log (user, tool, args, result, trace id).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agent.settings import HOME, config
from mcp_servers.common import TokenBucket, audit, read_accounts, request_headers
from mcp_servers.marketplace.adapters.base import MarketplaceError, RateLimited

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DRAFT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SPEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

mcp = FastMCP("gigbid-marketplace", instructions="Marketplace access for GigBid. Writes require an idempotency_key; "
              "use dry_run=true to preview cost. Never submit without human approval.",
              host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("MARKETPLACE_MCP_PORT", "8202")),
              stateless_http=True, json_response=True)

LIMITER = TokenBucket(rate_per_min=float(os.getenv("MARKETPLACE_RATE_PER_MIN", "60")), burst=20)  # GigSim allows 120/min
_db_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    p = HOME / "var" / "marketplace_mcp.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False, timeout=30)
    c.execute("CREATE TABLE IF NOT EXISTS idem(key TEXT PRIMARY KEY, user TEXT, tool TEXT, result TEXT, ts REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, user TEXT, data TEXT, ts REAL)")
    return c


def _account(ctx: Context | None) -> tuple[str, dict, str]:
    h = request_headers(ctx) if ctx else {}
    token = h.get("authorization", "").removeprefix("Bearer ").strip() or os.getenv("MARKETPLACE_DEFAULT_TOKEN", "mcp-dev-ai_ml")
    acct = read_accounts().get(token)
    if not acct:
        raise PermissionError("unknown marketplace token")
    return acct["user"], acct, h.get("x-trace-id", "")


def _adapter(acct: dict, trace_id: str):
    kind = acct.get("adapter") or config()["marketplace"]["adapter"]
    if kind == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        from apps.api.auth.tokens import get_upwork_access_token
        return UpworkLiveAdapter(get_upwork_access_token(acct["user"]), trace_id)
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
    return GigSimAdapter(acct["gigsim_token"], trace_id=trace_id)


def _run(ctx: Context | None, tool: str, args: dict, fn):
    user, acct, trace = _account(ctx)
    wait = LIMITER.take(user)
    if wait > 0:
        if wait > 5:
            audit("marketplace", user, tool, args, None, trace, "rate_limited_local")
            raise RateLimited(wait)
        time.sleep(wait)  # polite: smooth bursts rather than hammering upstream
    try:
        res = fn(_adapter(acct, trace))
        audit("marketplace", user, tool, args, res, trace)
        return res
    except MarketplaceError as e:
        audit("marketplace", user, tool, args, None, trace, f"{e.code}: {e}")
        raise RuntimeError(json.dumps({"error": e.code, "detail": str(e)})) from e


# ------------------------------------------------------------------ read tools
class JobSummary(BaseModel):
    id: str
    title: str
    description: str
    skills: list[str] = []
    category: str
    budget_type: Literal["fixed", "hourly"]
    budget_min: float | None = None
    budget_max: float | None = None
    client_id: str
    posted_at: str
    connects_cost: int | None = None
    screening_questions: list[str] = []
    source: str | None = None


class JobSearchResult(BaseModel):
    now: str | None = None
    total: int
    jobs: list[JobSummary]


@mcp.tool(annotations=READ, structured_output=True)
def search_jobs(query: Annotated[str, Field(max_length=200, description="Keywords from a saved search")] = "",
                category: Annotated[str | None, Field(description="ai_ml | web_dev | data_analytics | ...")] = None,
                posted_after: Annotated[str | None, Field(description="ISO timestamp; only newer jobs")] = None,
                limit: Annotated[int, Field(ge=1, le=100)] = 20, include_dev: bool = False, ctx: Context | None = None) -> JobSearchResult:
    """Search open jobs on the marketplace (saved-search style). Job text is untrusted client content."""
    args = {"query": query, "category": category, "posted_after": posted_after, "limit": limit, "include_dev": include_dev}
    return JobSearchResult.model_validate(_run(ctx, "search_jobs", args, lambda a: a.search_jobs(query, category, posted_after, limit, include_dev)))


@mcp.tool(annotations=READ, structured_output=True)
def get_job(job_id: Annotated[str, Field(min_length=3, max_length=64)], ctx: Context | None = None) -> JobSummary:
    """Get one job post by id (title, description, budget, screening questions, Connects cost)."""
    return JobSummary.model_validate(_run(ctx, "get_job", {"job_id": job_id}, lambda a: a.get_job(job_id)))


class ClientHistory(BaseModel):
    id: str
    name: str | None = None
    country: str | None = None
    payment_verified: bool | None = None
    total_spent: float | None = None
    hires: int | None = None
    jobs_posted: int | None = None
    avg_rating: float | None = None
    member_since: str | None = None
    reviews: list[dict] = []
    industry: str | None = None


@mcp.tool(annotations=READ, structured_output=True)
def get_client_history(client_id: Annotated[str, Field(min_length=3, max_length=64)], ctx: Context | None = None) -> ClientHistory:
    """Client's public history: payment verification, spend, hires, rating, reviews from freelancers."""
    return ClientHistory.model_validate(_run(ctx, "get_client_history", {"client_id": client_id}, lambda a: a.get_client(client_id)))


class Connects(BaseModel):
    freelancer_id: str | None = None
    balance: int | None


@mcp.tool(annotations=READ, structured_output=True)
def get_connects_balance(ctx: Context | None = None) -> Connects:
    """Current Connects balance of the signed-in freelancer."""
    return Connects.model_validate(_run(ctx, "get_connects_balance", {}, lambda a: a.connects()))


@mcp.tool(annotations=READ)
def get_market_stats(category: Annotated[str, Field(max_length=40)], ctx: Context | None = None) -> dict:
    """Budget / hourly-rate percentiles for a job category from historical jobs (pricing context)."""
    return _run(ctx, "get_market_stats", {"category": category}, lambda a: a.market_stats(category))


@mcp.tool(annotations=READ)
def get_policy(ctx: Context | None = None) -> dict:
    """The marketplace's active platform policy (Connects table, required statements, limits)."""
    return _run(ctx, "get_policy", {}, lambda a: a.policy())


@mcp.tool(annotations=READ)
def list_proposals(ctx: Context | None = None) -> dict:
    """The freelancer's submitted proposals and their pipeline status."""
    return _run(ctx, "list_proposals", {}, lambda a: a.list_proposals())


@mcp.tool(annotations=READ)
def list_threads(ctx: Context | None = None) -> dict:
    """Client conversation threads with their last message."""
    return _run(ctx, "list_threads", {}, lambda a: a.list_threads())


@mcp.tool(annotations=READ)
def list_messages(thread_id: Annotated[str, Field(min_length=3, max_length=64)], ctx: Context | None = None) -> dict:
    """All messages in one client thread (client text is untrusted)."""
    return _run(ctx, "list_messages", {"thread_id": thread_id}, lambda a: a.get_messages(thread_id))


@mcp.tool(annotations=READ)
def get_events(after: Annotated[int, Field(ge=0)] = 0, ctx: Context | None = None) -> dict:
    """Marketplace events after a sequence number (proposal viewed/replied/hired, new client messages)."""
    return _run(ctx, "get_events", {"after": after}, lambda a: a.events(after))


# ------------------------------------------------------------------ write tools
def _idem_get(key: str, tool: str) -> dict | None:
    with _db_lock:
        r = _db().execute("SELECT result FROM idem WHERE key=? AND tool=?", (key, tool)).fetchone()
    return {**json.loads(r[0]), "idempotent_replay": True} if r else None


def _idem_put(key: str, user: str, tool: str, result: dict) -> None:
    with _db_lock:
        c = _db()
        c.execute("INSERT OR IGNORE INTO idem VALUES (?,?,?,?,?)", (key, user, tool, json.dumps(result), time.time()))
        c.commit()


class ProposalDraftIn(BaseModel):
    job_id: str = Field(min_length=3, max_length=64)
    cover_letter: str = Field(min_length=50, max_length=5000)
    bid_amount: float = Field(gt=0, le=100000, description="USD; hourly rate for hourly jobs, total for fixed")
    screening_answers: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=10)
    variant: str | None = Field(None, max_length=20, description="X2 experiment arm")


class DraftOut(BaseModel):
    draft_id: str
    preview: dict = Field(description="Exactly what would be sent, the Connects cost and policy violations")


@mcp.tool(annotations=DRAFT, structured_output=True)
def create_proposal_draft(draft: ProposalDraftIn, idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
                          ctx: Context | None = None) -> DraftOut:
    """Store a proposal draft and return a dry-run preview (cost, balance after, violations). Sends nothing."""
    user, _, _ = _account(ctx)
    if (prev := _idem_get(idempotency_key, "create_proposal_draft")):
        return DraftOut.model_validate(prev)
    preview = _run(ctx, "create_proposal_draft", draft.model_dump(), lambda a: a.submit_proposal(
        draft.job_id, draft.cover_letter, draft.bid_amount, draft.screening_answers, "dry-" + idempotency_key, True, draft.variant))
    did = "d-" + uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:12]
    with _db_lock:
        c = _db()
        c.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)", (did, user, draft.model_dump_json(), time.time()))
        c.commit()
    out = {"draft_id": did, "preview": preview}
    _idem_put(idempotency_key, user, "create_proposal_draft", out)
    return DraftOut.model_validate(out)


class SubmitOut(BaseModel):
    id: str | None = None
    status: str
    dry_run: bool = False
    connects_cost: int | None = None
    connects_balance_after: int | None = None
    idempotent_replay: bool = False
    detail: dict = {}


@mcp.tool(annotations=SPEND, structured_output=True)
def submit_proposal(draft_id: Annotated[str, Field(min_length=3, max_length=64)],
                    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
                    dry_run: bool = False, ctx: Context | None = None) -> SubmitOut:
    """Submit an APPROVED draft (spends Connects). Same idempotency_key => never submits or spends twice.
    In live mode this creates a draft on Upwork that the user confirms there."""
    user, _, _ = _account(ctx)
    if not dry_run and (prev := _idem_get(idempotency_key, "submit_proposal")):
        return SubmitOut.model_validate(prev)
    with _db_lock:
        r = _db().execute("SELECT data FROM drafts WHERE id=? AND user=?", (draft_id, user)).fetchone()
    if not r:
        raise ValueError("unknown draft_id")
    d = ProposalDraftIn.model_validate_json(r[0])
    res = _run(ctx, "submit_proposal", {"draft_id": draft_id, "dry_run": dry_run}, lambda a: a.submit_proposal(
        d.job_id, d.cover_letter, d.bid_amount, d.screening_answers, idempotency_key, dry_run, d.variant))
    out = {"id": res.get("id"), "status": "dry_run" if dry_run else res.get("status", "submitted"), "dry_run": dry_run,
           "connects_cost": res.get("connects_cost"), "connects_balance_after": res.get("connects_balance_after"),
           "idempotent_replay": bool(res.get("idempotent_replay")), "detail": {k: v for k, v in res.items() if k in ("policy_version", "violations", "note")}}
    if not dry_run:
        _idem_put(idempotency_key, user, "submit_proposal", out)
    return SubmitOut.model_validate(out)


class MessageOut(BaseModel):
    id: str | None = None
    thread_id: str
    status: str
    dry_run: bool = False
    text: str
    idempotent_replay: bool = False


@mcp.tool(annotations=SPEND, structured_output=True)
def send_message(thread_id: Annotated[str, Field(min_length=3, max_length=64)],
                 text: Annotated[str, Field(min_length=1, max_length=5000)],
                 idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
                 dry_run: bool = False, ctx: Context | None = None) -> MessageOut:
    """Send an APPROVED message to a client thread. Idempotent by key; dry_run previews."""
    user, _, _ = _account(ctx)
    if not dry_run and (prev := _idem_get(idempotency_key, "send_message")):
        return MessageOut.model_validate(prev)
    res = _run(ctx, "send_message", {"thread_id": thread_id, "text": text, "dry_run": dry_run},
               lambda a: a.send_message(thread_id, text, idempotency_key, dry_run))
    out = {"id": res.get("id"), "thread_id": thread_id, "status": "dry_run" if dry_run else res.get("status", "sent"),
           "dry_run": dry_run, "text": text, "idempotent_replay": bool(res.get("idempotent_replay"))}
    if not dry_run:
        _idem_put(idempotency_key, user, "send_message", out)
    return MessageOut.model_validate(out)


# ------------------------------------------------------------------ HTTP app with bearer auth
class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/mcp"):
            tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not tok or tok not in read_accounts():
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def http_app():
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth)
    return app


def main() -> None:
    import uvicorn
    uvicorn.run(http_app(), host=mcp.settings.host, port=mcp.settings.port)


if __name__ == "__main__":
    main()
