from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])
REPLIED = {"replied", "interview", "hired"}


@router.get("", response_model=dict)
def analytics(user: dict = Depends(current_user)):
    with db.engine.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(select(db.inbox).where(db.inbox.c.user_id == user["id"]))]
        runs = [dict(r._mapping) for r in c.execute(select(db.runs).where(db.runs.c.user_id == user["id"], db.runs.c.kind == "bid"))]
    sub = [r for r in rows if r["proposal_id"]]
    by_cat: dict[str, dict] = defaultdict(lambda: {"submitted": 0, "replied": 0, "hired": 0, "connects": 0})
    by_arm: dict[str, dict] = defaultdict(lambda: {"submitted": 0, "replied": 0})
    for r in sub:
        k = r["category"] or "other"
        by_cat[k]["submitted"] += 1
        by_cat[k]["replied"] += r["pipeline"] in REPLIED
        by_cat[k]["hired"] += r["pipeline"] == "hired"
        by_cat[k]["connects"] += r["connects"] or 0
        a = r["variant"] or "-"
        by_arm[a]["submitted"] += 1
        by_arm[a]["replied"] += r["pipeline"] in REPLIED
    lat = [(r["usage"] or {}).get("elapsed_s") for r in runs if (r["usage"] or {}).get("elapsed_s")]
    cost = [(r["usage"] or {}).get("cost_usd", 0) for r in runs if r["usage"]]

    def p(xs, q):
        return round(statistics.quantiles(xs, n=100)[q - 1], 3) if len(xs) >= 2 else (round(xs[0], 3) if xs else None)
    return {
        "funnel": {"seen": len(rows), "bid_recommended": sum(r["action"] == "bid" for r in rows), "submitted": len(sub),
                   "replied": sum(r["pipeline"] in REPLIED for r in sub), "hired": sum(r["pipeline"] == "hired" for r in sub),
                   "scams_caught": sum(bool(r["is_scam"]) for r in rows)},
        "by_category": [{"category": k, **v, "reply_rate": round(v["replied"] / v["submitted"], 3) if v["submitted"] else None} for k, v in by_cat.items()],
        "by_arm": [{"arm": k, **v, "reply_rate": round(v["replied"] / v["submitted"], 3) if v["submitted"] else None} for k, v in by_arm.items()],
        "connects": {"spent": sum(r["connects"] or 0 for r in sub), "per_reply": round(sum(r["connects"] or 0 for r in sub) / max(1, sum(r["pipeline"] in REPLIED for r in sub)), 1)},
        "latency_s": {"p50": p(lat, 50), "p95": p(lat, 95), "n": len(lat)},
        "cost_usd": {"total": round(sum(cost), 5), "per_run_mean": round(sum(cost) / len(cost), 6) if cost else None},
        "top_rejection_reasons": Counter(r["reject_reason"] for r in rows if r["reject_reason"]).most_common(5),
    }
