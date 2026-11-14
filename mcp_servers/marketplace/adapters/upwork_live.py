"""Live Upwork adapter: talks to Upwork's OFFICIAL MCP server (https://mcp.upwork.com/mcp)
over Streamable HTTP via MultiServerMCPClient, using the user's OAuth 2.1 access token
(obtained in apps/api/auth/oauth_upwork.py and stored encrypted per user).

Rules enforced here (docs/RUNBOOK.md):
* reads only; the scheduler polls no more often than marketplace.live_poll_minutes;
* every write becomes a DRAFT on Upwork that the user must confirm there - never a final submit;
* no browser automation, no cookies, no scraping.

Upwork's tool names are discovered at runtime and mapped with TOOL_MAP so the
rest of GigBid sees the same port as with GigSim.
"""
from __future__ import annotations

import asyncio
import json
import os

from mcp_servers.marketplace.adapters.base import MarketplaceUnavailable, NotFound

UPWORK_MCP_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")
TOOL_MAP = {  # port operation -> candidate Upwork MCP tool names (first match wins)
    "search_jobs": ["search_jobs", "job_search", "searchJobs", "find_jobs"],
    "get_job": ["get_job", "get_job_details", "getJob", "job_details"],
    "get_client": ["get_client", "get_client_details", "client_history"],
    "connects": ["get_connects_balance", "connects_balance", "get_connects"],
    "draft_proposal": ["create_proposal_draft", "draft_proposal", "create_proposal"],
    "list_threads": ["list_rooms", "list_conversations", "list_threads", "messages_list_rooms"],
    "get_messages": ["get_room_messages", "list_messages", "get_messages"],
    "draft_message": ["create_message_draft", "draft_message", "send_message"],
}


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, access_token: str, trace_id: str = ""):
        self.token = access_token
        self.trace_id = trace_id
        self._tools = None

    async def _load(self):
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": UPWORK_MCP_URL,
                                                  "headers": {"Authorization": f"Bearer {self.token}"}}})
        tools = await client.get_tools()
        return {t.name: t for t in tools}

    def _call(self, op: str, args: dict) -> dict:
        try:
            if self._tools is None:
                self._tools = asyncio.run(self._load())
        except Exception as e:  # network / auth
            raise MarketplaceUnavailable(f"Upwork MCP unavailable: {e}") from e
        name = next((n for n in TOOL_MAP[op] if n in self._tools), None)
        if not name:
            raise NotFound(f"Upwork MCP exposes no tool for '{op}' (have: {sorted(self._tools)[:20]})")
        out = asyncio.run(self._tools[name].ainvoke(args))
        if isinstance(out, str):
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"text": out}
        return out if isinstance(out, dict) else {"result": out}

    def search_jobs(self, query, category, posted_after, limit, include_dev):
        return self._call("search_jobs", {"query": query, "limit": limit})

    def get_job(self, job_id):
        return self._call("get_job", {"job_id": job_id})

    def get_client(self, client_id):
        return self._call("get_client", {"client_id": client_id})

    def connects(self):
        return self._call("connects", {})

    def market_stats(self, category):
        return {"category": category, "fixed": None, "hourly_high": None, "sources": ["unavailable_in_live_mode"]}

    def policy(self):
        return {"version": "upwork-live", "required_phrases": [], "connects": None}

    def submit_proposal(self, job_id, cover_letter, bid_amount, screening_answers, idempotency_key, dry_run, variant):
        if dry_run:
            return {"dry_run": True, "job_id": job_id, "cover_letter": cover_letter, "bid_amount": bid_amount,
                    "connects_cost": None, "note": "Upwork shows the Connects cost when you confirm the draft."}
        res = self._call("draft_proposal", {"job_id": job_id, "cover_letter": cover_letter, "bid_amount": bid_amount,
                                            "screening_answers": screening_answers})
        return {**res, "status": "draft_created_confirm_on_upwork", "idempotent_replay": False}

    def list_proposals(self):
        return {"proposals": []}

    def list_threads(self):
        return self._call("list_threads", {})

    def get_messages(self, thread_id):
        return self._call("get_messages", {"room_id": thread_id})

    def send_message(self, thread_id, text, idempotency_key, dry_run):
        if dry_run:
            return {"dry_run": True, "thread_id": thread_id, "text": text}
        return {**self._call("draft_message", {"room_id": thread_id, "text": text}), "status": "draft_created_confirm_on_upwork"}

    def events(self, after):
        return {"events": []}
