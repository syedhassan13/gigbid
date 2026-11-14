"""Shared eval helpers: dev-set loading, IR metrics, result writing (evals/results/*.json)."""
from __future__ import annotations

import json
import math
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "evals" / "datasets"
RESULTS = ROOT / "evals" / "results"
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]


def load_dev(persona: str, limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in (DEV / f"dev_{persona}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def load_clients() -> dict[str, dict]:
    return {c["id"]: c for c in (json.loads(l) for l in (DEV / "dev_clients.jsonl").read_text().splitlines() if l.strip())}


def recall_at(ranked: list[str], gold: set[str], k: int) -> float:
    return len(set(ranked[:k]) & gold) / min(len(gold), k) if gold else 0.0


def mrr(ranked: list[str], gold: set[str]) -> float:
    for i, d in enumerate(ranked):
        if d in gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at(ranked: list[str], gold: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in gold)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), k)))
    return dcg / idcg if idcg else 0.0


def pctl(xs: list[float], q: int) -> float | None:
    if not xs:
        return None
    if len(xs) == 1:
        return round(xs[0], 4)
    return round(statistics.quantiles(xs, n=100, method="inclusive")[q - 1], 4)


def mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def env_info() -> dict:
    from agent.settings import config
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except Exception:
        commit = ""
    return {"commit": commit, "profile": config()["profile"], "rag_variant": config()["rag"]["variant"],
            "embeddings": config()["embeddings"]["model"], "reranker": config()["reranker"]["model"],
            "python": platform.python_version(), "machine": platform.processor() or platform.machine(), "cpu_count": os.cpu_count(),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}


def write(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps({"env": env_info(), **payload}, indent=2, default=str), encoding="utf-8")
    print(f"wrote {p.relative_to(ROOT)}")
    return p
