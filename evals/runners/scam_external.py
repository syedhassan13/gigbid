"""External (out-of-distribution) check of the Risk Assessor's scam rules on Kaggle
'Fake-Job-Posting-Detection' (adityammantri/trial-1, licence: Unknown -> used locally only,
never redistributed; only aggregate metrics are committed).

Caveats: general employment ads (not freelance gigs) with text lower-cased and punctuation
stripped ("david27gmailcom"), so our regex rules are expected to transfer poorly - this
measures that gap honestly.

    python -m evals.runners.scam_external [--n 2000]
"""
from __future__ import annotations

import argparse
import random

from agent.nodes.risk import assess
from evals.runners.common import ROOT, write

UNKNOWN_CLIENT = {"payment_verified": True, "total_spent": 1000, "hires": 3, "avg_rating": 4.7}  # neutral: test text rules only


def main() -> None:
    import pandas as pd
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000, help="rows per class")
    a = ap.parse_args()
    p = ROOT / "data/raw/trial-1/processed_labeled_dataset_without_encoding.xlsx"
    if not p.exists():
        raise SystemExit("download the Kaggle data first (scripts/download_kaggle.py)")
    df = pd.read_excel(p, usecols=["job_title", "job_desc", "skills_desc", "fraudulent"])
    rows = []
    for label in (0, 1):
        sub = df[df.fraudulent == label]
        rows += sub.sample(min(a.n, len(sub)), random_state=7).to_dict("records")
    random.Random(7).shuffle(rows)
    tp = fp = fn = tn = 0
    flags: dict[str, int] = {}
    for r in rows:
        job = {"id": "x", "title": str(r["job_title"]), "description": f"{r['job_desc']} {r['skills_desc']}"}
        rep = assess(job, UNKNOWN_CLIENT)
        pred, gold = rep.is_scam, bool(r["fraudulent"])
        tp += pred and gold
        fp += pred and not gold
        fn += (not pred) and gold
        tn += (not pred) and not gold
        for f in rep.flags:
            flags[f.code] = flags.get(f.code, 0) + 1
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    write("scam_external", {"dataset": "kaggle:adityammantri/trial-1 (Fake-Job-Posting-Detection, licence Unknown, local only)",
                            "n": len(rows), "class_counts": {"real": sum(not r["fraudulent"] for r in rows), "fake": sum(bool(r["fraudulent"]) for r in rows)},
                            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
                            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "flag_counts": flags})
    print(f"external scam rules: P={prec:.3f} R={rec:.3f} n={len(rows)}")


if __name__ == "__main__":
    main()
