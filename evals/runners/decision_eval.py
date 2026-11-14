"""B4 decisions: bid-or-skip F1, scam precision/recall, price inside the fair band, latency/cost
per job analysed - per persona and job type. Also writes the failed jobs for the failure taxonomy.

    python -m evals.runners.decision_eval [--limit 200] [--smoke]
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from evals.runners.common import PERSONAS, load_clients, load_dev, mean, pctl, write
from evals.runners.harness import analyse


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def classify_failure(j: dict, res: dict) -> str:
    g = j["gold"]
    act = res["decision"]["action"]
    if g["is_scam"] and not res["risk"]["is_scam"]:
        return "missed_scam"
    if not g["is_scam"] and res["risk"]["is_scam"]:
        return "false_scam"
    if g["action"] == "bid" and act != "bid":
        if res["fit"]["missing"]:
            return "wrong_skip:missed_evidence"
        return "wrong_skip:threshold"
    if g["action"] == "skip" and act == "bid":
        return "wrong_bid:" + g["job_type"]
    return "mispriced"


async def run(limit: int | None) -> dict:
    clients = load_clients()
    agg = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "scam_tp": 0, "scam_fp": 0, "scam_fn": 0, "price_in": 0, "price_n": 0})
    lat, cost, failures = [], [], []
    for persona in PERSONAS:
        for j in load_dev(persona, limit):
            res = await analyse(j, clients.get(j["client_id"], {}), persona)
            lat.append(res["latency_s"])
            cost.append(res["usage"]["cost_usd"])
            g = j["gold"]
            pred_bid = res["decision"]["action"] == "bid"
            gold_bid = g["action"] == "bid"
            for key in ("all", persona, f"type:{g['job_type']}"):
                a = agg[key]
                a["tp"] += pred_bid and gold_bid
                a["fp"] += pred_bid and not gold_bid
                a["fn"] += (not pred_bid) and gold_bid
                a["tn"] += (not pred_bid) and not gold_bid
                a["scam_tp"] += res["risk"]["is_scam"] and g["is_scam"]
                a["scam_fp"] += res["risk"]["is_scam"] and not g["is_scam"]
                a["scam_fn"] += (not res["risk"]["is_scam"]) and g["is_scam"]
                if pred_bid and gold_bid and g["fair_band"] and "price" in res:
                    a["price_n"] += 1
                    a["price_in"] += g["fair_band"][0] <= res["price"]["amount"] <= g["fair_band"][1]
            mispriced = pred_bid and gold_bid and g["fair_band"] and "price" in res and not (g["fair_band"][0] <= res["price"]["amount"] <= g["fair_band"][1])
            if pred_bid != gold_bid or res["risk"]["is_scam"] != g["is_scam"] or mispriced:
                failures.append({"job_id": j["id"], "persona": persona, "job_type": g["job_type"], "title": j["title"][:90],
                                 "gold_action": g["action"], "pred_action": res["decision"]["action"], "category": classify_failure(j, res),
                                 "reasons": res["decision"]["reasons"][:3], "fit": res["fit"]["fit_score"], "missing": res["fit"]["missing"][:4],
                                 "price": res.get("price", {}).get("amount"), "fair_band": g["fair_band"]})
    out = {}
    for k, a in agg.items():
        out[k] = {"bid": prf(a["tp"], a["fp"], a["fn"]), "accuracy": round((a["tp"] + a["tn"]) / max(1, a["tp"] + a["fp"] + a["fn"] + a["tn"]), 4),
                  "scam": prf(a["scam_tp"], a["scam_fp"], a["scam_fn"]),
                  "price_in_band": round(a["price_in"] / a["price_n"], 4) if a["price_n"] else None, "price_n": a["price_n"]}
    tax = defaultdict(int)
    for f in failures:
        tax[f["category"]] += 1
    return {"metrics": out, "latency_per_job_s": {"p50": pctl(lat, 50), "p95": pctl(lat, 95), "mean": mean(lat)},
            "cost_per_job_usd": {"mean": mean(cost), "p95": pctl(cost, 95)}, "n_jobs": len(lat),
            "failure_taxonomy": dict(tax), "failures": failures[:200]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    res = asyncio.run(run(10 if a.smoke else a.limit))
    m = res["metrics"]["all"]
    print(f"bid F1={m['bid']['f1']} acc={m['accuracy']} scam P={m['scam']['precision']} R={m['scam']['recall']} price_in_band={m['price_in_band']} "
          f"p95={res['latency_per_job_s']['p95']}s n={res['n_jobs']} taxonomy={res['failure_taxonomy']}")
    write("decisions" + ("_smoke" if a.smoke else ""), res)


if __name__ == "__main__":
    main()
