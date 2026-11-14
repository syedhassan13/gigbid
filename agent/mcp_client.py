"""MCP client discipline (A6): every agent gets only the tools it needs (allowlist by name),
calls have timeouts and bounded retries with backoff, and a dead server puts the
system in a clear degraded mode instead of crashing.

Transports
  http    MultiServerMCPClient over Streamable HTTP (docker compose / deployment)
  inproc  real MCP JSON-RPC over in-memory streams to the same FastMCP servers
          (tests, evals, single-container deploys). Set MCP_TRANSPORT.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from agent.tracing import current_trace_id

ALLOWLIST: dict[str, dict[str, list[str]]] = {
    "scout": {"marketplace": ["search_jobs", "get_job"]},
    "analyst": {},
    "risk": {"marketplace": ["get_client_history"]},
    "matcher": {"portfolio": ["search_evidence", "list_skills"]},
    "pricing": {"marketplace": ["get_market_stats", "get_connects_balance", "get_policy"]},
    "writer": {"portfolio": ["search_evidence", "get_case_study"]},
    "critic": {"portfolio": ["search_evidence"]},
    "compliance": {},
    "approval_gate": {"marketplace": ["create_proposal_draft", "submit_proposal", "get_policy"]},
    "liaison": {"marketplace": ["list_threads", "list_messages", "get_job", "send_message"],
                "workspace": ["free_slots", "create_tentative_hold", "create_email_draft"]},
    "pipeline": {"marketplace": ["list_proposals", "get_events", "list_threads", "get_connects_balance"]},
    "single_agent": {"marketplace": ["get_job", "get_client_history", "get_market_stats"], "portfolio": ["search_evidence"]},
}
WRITE_TOOLS = {"create_proposal_draft", "submit_proposal", "send_message", "create_tentative_hold", "create_email_draft"}


class ToolError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class ToolNotAllowed(ToolError):
    pass


class ServerUnavailable(ToolError):
    pass


def _urls() -> dict[str, str]:
    return {"portfolio": os.getenv("PORTFOLIO_MCP_URL", "http://127.0.0.1:8201/mcp"),
            "marketplace": os.getenv("MARKETPLACE_MCP_URL", "http://127.0.0.1:8202/mcp"),
            "workspace": os.getenv("WORKSPACE_MCP_URL", "http://127.0.0.1:8203/mcp")}


def _server_obj(server: str):
    if server == "portfolio":
        from mcp_servers.portfolio import server as m
    elif server == "marketplace":
        from mcp_servers.marketplace import server as m
    else:
        from mcp_servers.workspace import server as m
    return m.mcp


_DOWN: dict[str, float] = {}  # server -> time it was last seen down (degraded-mode banner)


def server_status() -> dict[str, str]:
    return {s: ("down" if time.time() - _DOWN.get(s, 0) < 60 else "up") for s in ("portfolio", "marketplace", "workspace")}


def _parse(result) -> dict | list:
    if getattr(result, "isError", False):
        text = " ".join(getattr(c, "text", "") for c in result.content)
        try:
            j = json.loads(text[text.find("{"):]) if "{" in text else {}
        except json.JSONDecodeError:
            j = {}
        code = j.get("error", "tool_error")
        if code == "unavailable":
            raise ServerUnavailable(code, j.get("detail", text))
        raise ToolError(code, j.get("detail", text))
    if result.structuredContent is not None:
        sc = result.structuredContent
        return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
    text = " ".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


async def call_tool(agent: str, server: str, tool: str, args: dict, *, marketplace_token: str | None = None,
                    user: str = "", timeout: float = 30, retries: int = 2) -> dict | list:
    if tool not in ALLOWLIST.get(agent, {}).get(server, []):
        raise ToolNotAllowed("not_allowed", f"agent '{agent}' may not call {server}.{tool}")
    transport = os.getenv("MCP_TRANSPORT", "inproc")
    headers = {"X-Trace-Id": current_trace_id.get() or "", "X-Gigbid-User": user}
    if server == "marketplace":
        headers["Authorization"] = f"Bearer {marketplace_token or os.getenv('MARKETPLACE_DEFAULT_TOKEN', 'mcp-dev-ai_ml')}"
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if transport == "http":
                from langchain_mcp_adapters.client import MultiServerMCPClient
                client = MultiServerMCPClient({server: {"transport": "streamable_http", "url": _urls()[server], "headers": headers}})
                async with client.session(server) as s:
                    res = await asyncio.wait_for(s.call_tool(tool, args), timeout)
            else:
                from mcp.shared.memory import create_connected_server_and_client_session as connect
                from mcp_servers.common import INPROC_HEADERS
                INPROC_HEADERS.set(headers)  # same headers the HTTP transport would send
                async with connect(_server_obj(server)._mcp_server) as s:
                    res = await asyncio.wait_for(s.call_tool(tool, args), timeout)
            out = _parse(res)
            _DOWN.pop(server, None)
            return out
        except ServerUnavailable as e:
            last = e
        except ToolError:
            raise
        except (asyncio.TimeoutError, OSError, ConnectionError) as e:
            last = e
        except Exception as e:  # transport-level failures (httpx, anyio) -> retry
            if "connect" in str(e).lower() or "timeout" in str(e).lower() or "unavailable" in str(e).lower():
                last = e
            else:
                raise
        if tool in WRITE_TOOLS and not args.get("idempotency_key"):
            break  # never blindly retry a non-idempotent write (all of ours carry keys)
        await asyncio.sleep(min(4, 0.5 * 2 ** attempt))
    _DOWN[server] = time.time()
    raise ServerUnavailable("unavailable", f"{server} MCP server unavailable: {last}")


async def langchain_tools(agent: str, marketplace_token: str | None = None):
    """LangChain tools filtered by the agent's allowlist (used by the single-agent ReAct baseline)."""
    from langchain_core.tools import StructuredTool

    tools = []
    for server, names in ALLOWLIST.get(agent, {}).items():
        mcp_obj = _server_obj(server)
        listed = {t.name: t for t in await mcp_obj.list_tools()}
        for n in names:
            t = listed[n]

            async def _fn(_server=server, _name=n, **kwargs):
                return json.dumps(await call_tool(agent, _server, _name, kwargs, marketplace_token=marketplace_token), default=str)[:6000]
            tools.append(StructuredTool.from_function(coroutine=_fn, name=n, description=t.description or n, args_schema=t.inputSchema))
    return tools
