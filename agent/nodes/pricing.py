"""Pricing Strategist (Marketplace read): bid from market statistics, client budget/spend and the
user's floor; decides whether the Connects cost is worth it."""
from __future__ import annotations

from agent.handoffs import PriceQuote
from agent.mcp_client import ServerUnavailable
from agent.nodes.base import cfg_val, node, profile_of
from agent.settings import config
from agent.state import trace_event


def quote(job: dict, persona: str, market: dict, client: dict, fit: float, user_prefs: dict | None = None) -> PriceQuote:
    prof = {**profile_of(persona), **(user_prefs or {})}
    floor, target = prof["rate_floor"], prof["target_rate"]
    lo, hi = job.get("budget_min") or 0, job.get("budget_max") or 0
    why = []
    if job.get("budget_type") == "hourly":
        mk = (market.get("hourly_high") or {}).get("p50")
        amount = max(floor, min(target, hi)) if hi else target
        why.append(f"hourly: floor ${floor}, target ${target}, client range ${lo:.0f}-${hi:.0f}")
        if mk:
            why.append(f"market median hourly max in {job.get('category')}: ${mk}")
            if amount < mk * 0.8 and hi >= mk:
                amount = min(hi, mk)
                why.append("raised toward market median (client budget allows)")
        unit = "hourly"
    else:
        mk = (market.get("fixed") or {}).get("p50")
        amount = hi * (1 + config()["pricing"]["fixed_markup_over_budget"]) * (0.95 if fit < 0.75 else 1.0)
        amount = max(amount, floor * config()["decision"]["min_fixed_hours_at_floor"])
        why.append(f"fixed: client budget up to ${hi:.0f}; {'slight discount for partial fit' if fit < 0.75 else 'full budget for strong fit'}")
        if mk:
            why.append(f"market median fixed budget in {job.get('category')}: ${mk}")
        unit = "fixed"
    if (client.get("total_spent") or 0) > 20000:
        why.append(f"client has spent ${client['total_spent']:,} - established buyer")
    cc = job.get("connects_cost")
    cusd = (cc or 0) * config()["pricing"]["connect_usd"]
    worth = fit >= config()["decision"]["watch_fit"]
    why.append(f"{cc} Connects (≈${cusd:.2f}) {'worth it' if worth else 'not worth it'} at fit {fit:.2f}")
    return PriceQuote(amount=round(amount, 0), unit=unit, rationale=why, connects_cost=cc, connects_usd=round(cusd, 2), worth_connects=worth, market=market)


@node("pricing")
async def pricing(state: dict, cfg: dict, store) -> dict:
    port = cfg_val(cfg, "port")
    job = state["job"]
    try:
        market = await port.market_stats(job.get("category", "other"))
    except ServerUnavailable:
        market = {}
    q = quote(job, state["persona"], market, state.get("client") or {}, state["analyses"]["fit"]["fit_score"], cfg_val(cfg, "user_prefs"))
    return {"price": q.model_dump(), "trace": trace_event("pricing", "observation", amount=q.amount, unit=q.unit, rationale=q.rationale)}
