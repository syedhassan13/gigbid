"""Collect dev jobs where the shipped retriever misses ALL gold evidence in the top 5 (failure taxonomy input)."""
from __future__ import annotations

from evals.runners.common import PERSONAS, load_dev, recall_at, write
from rag.retriever import retrieve


def main() -> None:
    misses = []
    n = 0
    for p in PERSONAS:
        for j in [j for j in load_dev(p) if j["gold"]["evidence"]][:60]:
            n += 1
            res = retrieve(j, p, k=10, variant="v_best")
            ranked = [e.doc_id for e in res.evidence]
            if recall_at(ranked, set(j["gold"]["evidence"]), 5) == 0:
                misses.append({"job_id": j["id"], "persona": p, "job_type": j["gold"]["job_type"], "title": j["title"][:90],
                               "gold_project": j["gold"]["target_project"], "top5": ranked[:5], "requirements": j["gold"]["requirements"]})
    write("rag_failures", {"variant": "v_best", "n_jobs": n, "n_zero_recall": len(misses), "misses": misses})
    print(len(misses), "of", n)


if __name__ == "__main__":
    main()
