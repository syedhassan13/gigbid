"""B4 retrieval metrics for every RAG variant on the dev set (per persona and job type).

    python -m evals.runners.rag_eval [--variants v0_naive,v2_hybrid] [--limit 60] [--smoke]
Gold = evidence documents of the project the job was generated from (+ that project's sibling
case/repo and its won/replied proposals). Metrics are computed at document level.
"""
from __future__ import annotations

import argparse
import time
from collections import defaultdict

from evals.runners.common import PERSONAS, load_dev, mean, mrr, ndcg_at, pctl, recall_at, write
from rag.retriever import VARIANTS, retrieve


def run(variants: list[str], limit: int | None, job_types: set[str] | None = None) -> dict:
    out: dict = {"variants": {}}
    for v in variants:
        per = defaultdict(lambda: defaultdict(list))
        lat = []
        for persona in PERSONAS:
            jobs = [j for j in load_dev(persona) if j["gold"]["evidence"] and (not job_types or j["gold"]["job_type"] in job_types)]
            for j in jobs[:limit] if limit else jobs:
                gold = set(j["gold"]["evidence"])
                t0 = time.time()
                res = retrieve(j, persona, k=10, variant=v)
                lat.append(time.time() - t0)
                ranked = [e.doc_id for e in res.evidence]
                for key in (persona, f"type:{j['gold']['job_type']}", "all"):
                    per[key]["recall@5"].append(recall_at(ranked, gold, 5))
                    per[key]["mrr"].append(mrr(ranked, gold))
                    per[key]["ndcg@10"].append(ndcg_at(ranked, gold, 10))
        out["variants"][v] = {"n": len(per["all"]["mrr"]), "p50_latency_s": pctl(lat[1:] or lat, 50), "p95_latency_s": pctl(lat[1:] or lat, 95),
                              "breakdown": {k: {m: mean(xs) for m, xs in d.items()} for k, d in per.items()}}
        a = out["variants"][v]["breakdown"]["all"]
        print(f"{v:16s} R@5={a['recall@5']:.3f} MRR={a['mrr']:.3f} nDCG@10={a['ndcg@10']:.3f} p95={out['variants'][v]['p95_latency_s']}s n={out['variants'][v]['n']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--limit", type=int, default=None, help="jobs per persona")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default="rag_variants")
    a = ap.parse_args()
    limit = 10 if a.smoke else a.limit
    res = run(a.variants.split(","), limit)
    res["hypothesis"] = ("H-B: requirement decomposition + hybrid retrieval (+rerank, outcome boost, contextual chunks) raises evidence "
                         "Recall@5 by >= 15 points over V0 on jobs with four or more requirements (job_type=multi_req).")
    res["limit_per_persona"] = limit
    write(a.out + ("_smoke" if a.smoke else ""), res)


if __name__ == "__main__":
    main()
