"""Scout: run saved searches on schedule, de-duplicate (content hash), queue new jobs.
Inside the bid graph it is the intake node that loads the job + client through the port."""
from __future__ import annotations

import hashlib
import re

from agent.marketplace_port import MarketplacePort
from agent.mcp_client import ServerUnavailable
from agent.nodes.base import cfg_val, node
from agent.settings import config
from agent.state import trace_event


def content_hash(job: dict) -> str:
    norm = re.sub(r"\s+", " ", (job.get("title", "") + "|" + job.get("description", "")).lower()).strip()
    return hashlib.sha1(norm.encode()).hexdigest()


async def scout_saved_searches(port: MarketplacePort, persona: str, seen_hashes: set[str], posted_after: str | None = None,
                               include_dev: bool = False, limit: int = 20) -> list[dict]:
    """Returns NEW unique jobs across the persona's saved searches (dedup by id and by content hash)."""
    found: dict[str, dict] = {}
    for q in config()["scout"]["saved_searches"].get(persona, []):
        res = await port.search_jobs(query=q, posted_after=posted_after, limit=limit, include_dev=include_dev)
        for j in res.get("jobs", []):
            h = content_hash(j)
            if h in seen_hashes or j["id"] in found:
                continue
            seen_hashes.add(h)
            found[j["id"]] = {**j, "content_hash": h}
    return list(found.values())


@node("intake", timeout=60)
async def intake(state: dict, cfg: dict, store) -> dict:
    port: MarketplacePort = cfg_val(cfg, "port")
    try:
        job = state.get("job") or await port.get_job(state["job_id"])
        client = await port.client_history(job["client_id"], agent="risk")
    except ServerUnavailable as e:
        return {"status": "dead_letter", "error": f"marketplace unavailable: {e.detail}", "trace": trace_event("intake", "degraded", error=str(e))}
    return {"job": job, "client": client, "status": "analysing",
            "trace": trace_event("intake", "tool_result", tool="get_job+get_client_history", job_id=job["id"], client_id=job["client_id"])}
