"""Eval harness: runs the SAME node functions the bid graph uses, in graph order, without the
marketplace (job + client come from the committed dev set, market stats from the committed
pricing_stats.json) so evaluations are reproducible and do not hit GigSim's rate limits."""
from __future__ import annotations

import json
import time

from agent.nodes.analyst import analyst
from agent.nodes.compliance import compliance
from agent.nodes.critic import after_critic, critic, verifier
from agent.nodes.decide import decide_bid
from agent.nodes.matcher import match
from agent.nodes.pricing import quote
from agent.nodes.risk import assess
from agent.nodes.writer import writer
from agent.tracing import start_run
from evals.runners.common import DEV

_STATS = json.loads((DEV / "pricing_stats.json").read_text())["stats"]


def market_for(category: str) -> dict:
    st = _STATS.get(category) or _STATS.get("_all", {})
    return {"category": category, "fixed": st.get("fixed"), "hourly_high": st.get("hourly_high")}


def _merge(state: dict, upd: dict) -> dict:
    s = dict(state)
    for k, v in (upd or {}).items():
        if k == "analyses":
            s["analyses"] = {**s.get("analyses", {}), **v}
        elif k in ("critiques", "trace"):
            s[k] = s.get(k, []) + v
        elif k in ("steps", "tokens"):
            s[k] = s.get(k, 0) + v
        elif k == "cost_usd":
            s[k] = s.get(k, 0.0) + v
        else:
            s[k] = v
    return s


async def analyse(job: dict, client: dict, persona: str, with_analyst: bool = False) -> dict:
    usage = start_run()
    t0 = time.time()
    risk = assess(job, client)
    fit = await match(job, persona)
    dec = decide_bid(job, risk.model_dump(), fit.model_dump(), persona)
    out = {"risk": risk.model_dump(), "fit": fit.model_dump(), "decision": dec.model_dump()}
    if with_analyst:
        st = {"job": job, "persona": persona}
        out["job_spec"] = (await analyst(st, {"configurable": {}}, store=None))["analyses"]["job_spec"]
    if dec.action == "bid":
        out["price"] = quote(job, persona, market_for(job.get("category", "other")), client, fit.fit_score).model_dump()
    out["latency_s"] = round(time.time() - t0, 3)
    out["usage"] = usage.snapshot()
    return out


async def propose(job: dict, client: dict, persona: str, arm: str | None = None, store=None) -> dict:
    """Full drafting path for a job we bid on: analyst -> pricing -> writer -> verifier -> critic loop -> compliance."""
    usage = start_run()
    t0 = time.time()
    cfg = {"configurable": {"thread_id": f"eval:{job['id']}:{arm}", "persona": persona}}
    risk = assess(job, client)
    fit = await match(job, persona)
    s: dict = {"job": job, "client": client, "persona": persona, "user_id": "eval", "analyses": {"risk": risk.model_dump(), "fit": fit.model_dump()}}
    s = _merge(s, await analyst(s, cfg, store=store))
    s["price"] = quote(job, persona, market_for(job.get("category", "other")), client, fit.fit_score).model_dump()
    if arm:
        s["draft"] = {"variant": arm}
    while True:
        s = _merge(s, await writer(s, cfg, store=store))
        s = _merge(s, await verifier(s, cfg, store=store))
        s = _merge(s, await critic(s, cfg, store=store))
        if after_critic(s) != "revise":
            break
    s = _merge(s, await compliance(s, cfg, store=store))
    return {"state": s, "latency_s": round(time.time() - t0, 3), "usage": usage.snapshot()}
