"""The single marketplace interface (R1). The graph only talks to this port; the port only
talks to the Marketplace MCP server; the server picks the adapter (GigSim | Upwork live)
from config. Switching to live mode changes config + the user's connected account, not code.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent.mcp_client import call_tool


@dataclass
class MarketplacePort:
    token: str              # the user's marketplace MCP bearer token (maps to GigSim or Upwork account server-side)
    user: str = ""

    async def _c(self, agent: str, tool: str, **args):
        return await call_tool(agent, "marketplace", tool, args, marketplace_token=self.token, user=self.user)

    # reads
    async def search_jobs(self, query: str = "", category: str | None = None, posted_after: str | None = None, limit: int = 20,
                          include_dev: bool = False, agent: str = "scout"):
        return await self._c(agent, "search_jobs", query=query, category=category, posted_after=posted_after, limit=limit, include_dev=include_dev)

    async def get_job(self, job_id: str, agent: str = "scout"):
        return await self._c(agent, "get_job", job_id=job_id)

    async def client_history(self, client_id: str, agent: str = "risk"):
        return await self._c(agent, "get_client_history", client_id=client_id)

    async def market_stats(self, category: str, agent: str = "pricing"):
        return await self._c(agent, "get_market_stats", category=category)

    async def connects(self, agent: str = "pricing"):
        return await self._c(agent, "get_connects_balance")

    async def policy(self, agent: str = "pricing"):
        return await self._c(agent, "get_policy")

    async def proposals(self):
        return await self._c("pipeline", "list_proposals")

    async def events(self, after: int = 0):
        return await self._c("pipeline", "get_events", after=after)

    async def threads(self, agent: str = "liaison"):
        return await self._c(agent, "list_threads")

    async def messages(self, thread_id: str):
        return await self._c("liaison", "list_messages", thread_id=thread_id)

    # writes (only reachable from approval-gated nodes)
    async def create_draft(self, draft: dict, idempotency_key: str):
        return await self._c("approval_gate", "create_proposal_draft", draft=draft, idempotency_key=idempotency_key)

    async def submit(self, draft_id: str, idempotency_key: str, dry_run: bool = False):
        return await self._c("approval_gate", "submit_proposal", draft_id=draft_id, idempotency_key=idempotency_key, dry_run=dry_run)

    async def send_message(self, thread_id: str, text: str, idempotency_key: str, dry_run: bool = False):
        return await self._c("liaison", "send_message", thread_id=thread_id, text=text, idempotency_key=idempotency_key, dry_run=dry_run)


def persona_token(persona: str) -> str:
    return f"mcp-dev-{persona}"
