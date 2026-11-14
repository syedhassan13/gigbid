"""Bid-or-skip decision node: joins the three parallel analyses. Thresholds from config."""
from __future__ import annotations

from agent.handoffs import BidDecision
from agent.nodes.base import node, profile_of
from agent.settings import config
from agent.state import trace_event


def decide_bid(job: dict, risk: dict, fit: dict, persona: str, autonomy: str = "suggest") -> BidDecision:
    d = config()["decision"]
    prof = profile_of(persona)
    floor = prof["rate_floor"]
    reasons = []
    hi = job.get("budget_max") or 0
    connects_usd = (job.get("connects_cost") or 0) * config()["pricing"]["connect_usd"]
    p_win = 0.04 + 0.25 * fit["fit_score"]
    value = hi * (20 if job.get("budget_type") == "hourly" else 1)
    ev = round(p_win * value * 0.1 - connects_usd, 2)  # 10% margin proxy
    if risk["is_scam"] or risk["risk_score"] >= d["risk_skip"]:
        reasons.append(f"risk {risk['risk_score']:.2f}: {risk['summary']}")
        return BidDecision(action="skip", reasons=reasons, expected_value_usd=ev, auto=autonomy == "auto_skip_low_fit")
    if job.get("budget_type") == "hourly" and hi < floor * d["min_hourly_multiple_of_floor"]:
        reasons.append(f"hourly max ${hi} below your floor ${floor}")
        return BidDecision(action="skip", reasons=reasons, expected_value_usd=ev, auto=autonomy == "auto_skip_low_fit")
    if job.get("budget_type") == "fixed" and hi < floor * d["min_fixed_hours_at_floor"]:
        reasons.append(f"fixed budget ${hi} < {d['min_fixed_hours_at_floor']}h at your floor (${floor * d['min_fixed_hours_at_floor']})")
        return BidDecision(action="skip", reasons=reasons, expected_value_usd=ev, auto=autonomy == "auto_skip_low_fit")
    reasons += fit.get("reasons", [])[:3]
    if fit["fit_score"] >= d["bid_fit"] and ev >= d["expected_value_min_usd"]:
        return BidDecision(action="bid", reasons=[f"fit {fit['fit_score']:.2f} ≥ {d['bid_fit']}"] + reasons, expected_value_usd=ev)
    if fit["fit_score"] >= d["watch_fit"]:
        return BidDecision(action="watch", reasons=[f"fit {fit['fit_score']:.2f} borderline"] + reasons, expected_value_usd=ev)
    return BidDecision(action="skip", reasons=[f"fit {fit['fit_score']:.2f} < {d['watch_fit']}; missing: {', '.join(fit.get('missing', [])[:3])}"],
                       expected_value_usd=ev, auto=autonomy == "auto_skip_low_fit")


@node("decide")
async def decide(state: dict, cfg: dict, store) -> dict:
    a = state["analyses"]
    dec = decide_bid(state["job"], a["risk"], a["fit"], state["persona"], state.get("autonomy", "suggest"))
    if state.get("force_bid") and dec.action != "bid" and not a["risk"]["is_scam"]:
        dec = BidDecision(action="bid", reasons=["user chose to bid anyway"] + dec.reasons, expected_value_usd=dec.expected_value_usd)
    status = {"bid": "analysing", "watch": "watch", "skip": "skipped"}[dec.action]
    return {"decision": dec.model_dump(), "status": status, "trace": trace_event("decide", "decision", action=dec.action, reasons=dec.reasons)}
