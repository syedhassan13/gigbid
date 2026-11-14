"""R&D B ablation: remove one component of the shipped pipeline at a time.

    python -m evals.runners.ablation [--limit 60]
"""
from __future__ import annotations

import argparse
import dataclasses
import time
from collections import defaultdict

from evals.runners.common import PERSONAS, load_dev, mean, mrr, ndcg_at, recall_at, write
from rag.pipeline import run as run_pipeline
from rag.retriever import variant_config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    best = variant_config("v_best")
    ablations = {
        "full (v_best)": best,
        "- decomposition": dataclasses.replace(best, query="whole", name="abl_no_decomp"),
        "- hybrid (dense only)": dataclasses.replace(best, retrieval="dense", name="abl_dense"),
        "- reranker": dataclasses.replace(best, rerank=False, name="abl_no_rerank"),
        "- outcome boost": dataclasses.replace(best, outcome_boost=False, name="abl_no_outcome"),
        "- contextual chunks": dataclasses.replace(best, chunking="structure", name="abl_no_context"),
    }
    out = {}
    for label, cfg in ablations.items():
        per = defaultdict(lambda: defaultdict(list))
        t0 = time.time()
        for persona in PERSONAS:
            jobs = [j for j in load_dev(persona) if j["gold"]["evidence"]]
            for j in jobs[: a.limit] if a.limit else jobs:
                ranked = [e.doc_id for e in run_pipeline(cfg, j, persona, 10).evidence]
                gold = set(j["gold"]["evidence"])
                for key in ("all", persona, f"type:{j['gold']['job_type']}"):
                    per[key]["recall@5"].append(recall_at(ranked, gold, 5))
                    per[key]["mrr"].append(mrr(ranked, gold))
                    per[key]["ndcg@10"].append(ndcg_at(ranked, gold, 10))
        out[label] = {k: {m: mean(v) for m, v in d.items()} for k, d in per.items()}
        out[label]["seconds"] = round(time.time() - t0, 1)
        print(f"{label:24s} R@5={out[label]['all']['recall@5']:.3f} MRR={out[label]['all']['mrr']:.3f} nDCG={out[label]['all']['ndcg@10']:.3f}")
    write("ablation", {"ablations": out, "limit_per_persona": a.limit})


if __name__ == "__main__":
    main()
