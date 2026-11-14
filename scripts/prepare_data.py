"""Build GigSim seed data and the dev evaluation set.

Inputs
  data/raw/**.csv           Kaggle datasets (optional; see docs/DATA_CARD.md)
  data/personas/*           synthetic persona corpora (scripts/generate_personas.py)
Outputs (data/processed/, git-ignored except where noted)
  pricing_stats.json        budget / hourly percentiles per category (REAL if Kaggle present)
  kaggle_profile.json       which raw files were used, row counts, columns detected
  historical_jobs.jsonl     ~1,500 historical jobs for pricing context (real titles+budgets when available)
  stream_jobs.jsonl         live-stream jobs GigSim releases over time (dupes, scams, injections)
  clients.jsonl             all clients referenced by any job
  evals/datasets/dev_<persona>.jsonl   200 gold-labelled jobs per persona (committed)
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gigsim import generator as G  # noqa: E402

PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
DEV = ROOT / "evals" / "datasets"

CATEGORY_KEYWORDS = {
    "ai_ml": ["machine learning", " ml ", "ai ", "artificial intelligence", "llm", "gpt", "chatbot", "nlp", "computer vision",
              "deep learning", "data scien", "langchain", "rag", "openai", "pytorch", "tensorflow"],
    "web_dev": ["react", "next.js", "nextjs", "node", "django", "laravel", "website", "web app", "full stack", "full-stack",
                "frontend", "front-end", "backend", "back-end", "shopify", "wordpress", "javascript", "typescript", "php"],
    "data_analytics": ["power bi", "tableau", "excel", "data analy", "sql", "dashboard", "dbt", "looker", "analytics", "etl",
                       "spreadsheet", "google sheets", "bigquery"],
    "design": ["logo", "graphic", "figma", "ui/ux", "ux", "illustrat", "brand"],
    "writing": ["writer", "writing", "content", "copywrit", "article", "blog", "translat", "proofread"],
    "marketing": ["seo", "social media", "marketing", "ads", "facebook", "instagram", "lead generation"],
    "video": ["video", "editing", "animation", "youtube", "voice"],
    "mobile": ["ios", "android", "flutter", "react native", "mobile app", "swift", "kotlin"],
    "admin": ["virtual assistant", "data entry", "customer service", "bookkeep", "admin"],
}


def categorize(title: str) -> str:
    t = f" {title.lower()} "
    best, score = "other", 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        s = sum(kw in t for kw in kws)
        if s > score:
            best, score = cat, s
    return best


def _num(v) -> float | None:
    if v is None:
        return None
    s = re.sub(r"[^0-9.]", "", str(v))
    try:
        x = float(s) if s else None
    except ValueError:
        return None
    return x if x and 0 < x < 1_000_000 else None


def _find(cols: list[str], *needles: str) -> str | None:
    low = {c.lower().strip(): c for c in cols}
    for n in needles:
        for lc, c in low.items():
            if n in lc:
                return c
    return None


def load_kaggle(max_rows_per_file: int = 300_000) -> tuple[list[dict], dict]:
    """Read every CSV under data/raw with robust column detection."""
    rows, profile = [], {"files": []}
    if not RAW.exists():
        return rows, profile
    csv.field_size_limit(10_000_000)
    for path in sorted(RAW.rglob("*.csv")):
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            c_title = _find(cols, "title", "job_title", "job title", "name")
            c_desc = _find(cols, "description", "desc", "summary")
            c_budget = _find(cols, "budget", "job_cost", "fixed_price", "price", "amount")
            c_lo = _find(cols, "hourly_low", "start_rate", "min_hourly", "hourly rate low", "rate_low")
            c_hi = _find(cols, "hourly_high", "end_rate", "max_hourly", "hourly rate high", "rate_high")
            c_rate = _find(cols, "hourly_rate", "hourly rate", "rate")
            c_hourly = _find(cols, "is_hourly", "payment_type", "job type", "job_type", "payment type")
            c_spent = _find(cols, "spent")
            c_conn = _find(cols, "connects_num")
            c_rating = _find(cols, "rating")
            c_payver = _find(cols, "payment_situation")
            c_skills = _find(cols, "skills", "tags", "keywords")
            c_country = _find(cols, "country", "location")
            n = 0
            for r in reader:
                if n >= max_rows_per_file:
                    break
                n += 1
                title = (r.get(c_title) or "").strip() if c_title else ""
                hourly_flag = str(r.get(c_hourly, "")).lower() if c_hourly else ""
                lo, hi = _num(r.get(c_lo)) if c_lo else None, _num(r.get(c_hi)) if c_hi else None
                rate = _num(r.get(c_rate)) if c_rate and not (lo or hi) else None
                rows.append({"src": path.parent.name, "title": title[:200],
                             "description": (r.get(c_desc) or "")[:3000] if c_desc else "",
                             "budget": _num(r.get(c_budget)) if c_budget else None,
                             "hourly_low": lo or rate, "hourly_high": hi or rate,
                             "is_hourly": ("true" in hourly_flag or "hour" in hourly_flag) or bool(lo or hi or rate),
                             "skills": (r.get(c_skills) or "")[:300] if c_skills else "",
                             "country": (r.get(c_country) or "") if c_country else "",
                             "client_spent": _num(r.get(c_spent)) if c_spent else None,
                             "connects": _num(r.get(c_conn)) if c_conn else None,
                             "client_rating": _num(r.get(c_rating)) if c_rating else None,
                             "payment_verified": ("verified" in str(r.get(c_payver, "")).lower() and "un" not in str(r.get(c_payver, "")).lower()) if c_payver else None})
            profile["files"].append({"file": str(path.relative_to(ROOT)), "rows_read": n, "columns": cols[:40],
                                     "detected": {"title": c_title, "description": c_desc, "budget": c_budget,
                                                  "hourly_low": c_lo, "hourly_high": c_hi, "rate": c_rate, "skills": c_skills}})
    return rows, profile


def pct(xs: list[float]) -> dict:
    if len(xs) < 20:
        return {}
    xs = sorted(xs)
    q = statistics.quantiles(xs, n=20)
    return {"n": len(xs), "p10": round(q[1], 1), "p25": round(q[4], 1), "p50": round(q[9], 1), "p75": round(q[14], 1), "p90": round(q[17], 1)}


def pricing_stats(rows: list[dict]) -> dict:
    by: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        if not r["title"]:
            continue
        cat = categorize(r["title"] + " " + r["skills"])
        for key in (cat, "_all"):
            d = by.setdefault(key, {"fixed": [], "hourly_low": [], "hourly_high": []})
            if r["is_hourly"]:
                if r["hourly_low"] and r["hourly_low"] < 500:
                    d["hourly_low"].append(r["hourly_low"])
                if r["hourly_high"] and r["hourly_high"] < 500:
                    d["hourly_high"].append(r["hourly_high"])
            elif r["budget"] and r["budget"] < 100_000:
                d["fixed"].append(r["budget"])
    out = {k: {m: pct(v) for m, v in d.items()} for k, d in by.items()}
    return {k: v for k, v in out.items() if any(v.values())}


SYNTH_STATS = {  # used ONLY when no Kaggle data is present; flagged in pricing_stats.json
    "_all": {"fixed": {"p25": 100, "p50": 300, "p75": 800, "p90": 2000}, "hourly_low": {"p50": 15}, "hourly_high": {"p50": 35}},
    "ai_ml": {"fixed": {"p25": 250, "p50": 800, "p75": 2000, "p90": 5000}, "hourly_low": {"p50": 25}, "hourly_high": {"p50": 60}},
    "web_dev": {"fixed": {"p25": 200, "p50": 600, "p75": 1500, "p90": 4000}, "hourly_low": {"p50": 20}, "hourly_high": {"p50": 45}},
    "data_analytics": {"fixed": {"p25": 100, "p50": 350, "p75": 900, "p90": 2000}, "hourly_low": {"p50": 15}, "hourly_high": {"p50": 35}},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--dev-per-persona", type=int, default=200)
    ap.add_argument("--historical", type=int, default=1500)
    ap.add_argument("--stream", type=int, default=300)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    PROC.mkdir(parents=True, exist_ok=True)
    DEV.mkdir(parents=True, exist_ok=True)

    rows, kprofile = load_kaggle()
    stats = pricing_stats(rows) if rows else {}
    stats_source = "kaggle" if stats else "synthetic_fallback"
    committed = DEV / "pricing_stats.json"
    if not stats and committed.exists() and json.loads(committed.read_text()).get("source", "").startswith("kaggle"):
        stats = json.loads(committed.read_text())["stats"]  # deployments ship only the committed Kaggle aggregates
        stats_source = "kaggle (committed aggregates)"
    if not stats:
        stats = SYNTH_STATS
    kprofile["total_rows"] = len(rows)
    kprofile["client_stats"] = {
        "client_spent_usd": pct([r["client_spent"] for r in rows if r.get("client_spent")]),
        "connects_per_job": pct([r["connects"] for r in rows if r.get("connects")]),
        "client_rating": pct([r["client_rating"] for r in rows if r.get("client_rating")]),
        "payment_verified_share": round(sum(bool(r.get("payment_verified")) for r in rows if r.get("payment_verified") is not None)
                                        / max(1, sum(r.get("payment_verified") is not None for r in rows)), 3)}
    kprofile["pricing_stats_source"] = stats_source
    (PROC / "pricing_stats.json").write_text(json.dumps({"source": stats_source, "stats": stats}, indent=2))
    (PROC / "kaggle_profile.json").write_text(json.dumps(kprofile, indent=2))
    # committed copy of the aggregate stats (derived, non-identifying) for reproducibility
    (DEV / "pricing_stats.json").write_text(json.dumps({"source": stats_source, "stats": stats}, indent=2))

    titles_by_cat: dict[str, list[str]] = {}
    for r in rows:
        if r["title"]:
            titles_by_cat.setdefault(categorize(r["title"]), []).append(r["title"])

    personas = {p: G.load_persona(p) for p in ("ai_ml", "fullstack", "data_analyst")}
    clients: dict[str, dict] = {}
    t0 = datetime(2026, 10, 1)

    # 1) historical jobs: real Kaggle rows when available (title/budget real; description may be empty)
    hist = []
    real = [r for r in rows if r["title"] and (r["budget"] or r["hourly_high"])]
    rng.shuffle(real)
    for i, r in enumerate(real[: args.historical]):
        job = {"title": r["title"], "description": r["description"] or f"(Kaggle record without description) {r['title']}",
               "skills": [s.strip() for s in re.split(r"[,;|]", r["skills"]) if s.strip()][:8], "category": categorize(r["title"]),
               "budget_type": "hourly" if r["is_hourly"] else "fixed",
               "budget_min": r["hourly_low"] or (r["budget"] or 0) * 0.8, "budget_max": r["hourly_high"] or r["budget"] or 0,
               "screening_questions": [], "source": f"kaggle:{r['src']}", "gold": {"is_scam": False}}
        job, cl = G.finalize(job, rng, (t0 - timedelta(days=rng.randint(1, 120))).isoformat())
        job.pop("gold", None)
        hist.append(job)
        clients[cl["id"]] = cl
    while len(hist) < args.historical:  # synthetic top-up when Kaggle is absent
        p = rng.choice(list(personas))
        prof, projs, props = personas[p]
        job = G.make_relevant_job(p, prof, projs, props, stats, rng) if rng.random() < .6 else G.make_offdomain_job(p, stats, rng)
        job, cl = G.finalize(job, rng, (t0 - timedelta(days=rng.randint(1, 120))).isoformat())
        job.pop("gold", None)
        hist.append(job)
        clients[cl["id"]] = cl
    (PROC / "historical_jobs.jsonl").write_text("\n".join(json.dumps(j) for j in hist) + "\n")

    # 2) dev set per persona with gold labels
    mix = [("relevant", .42), ("vague", .08), ("low_budget", .06), ("offdomain", .22), ("scam", .11), ("injection", .11)]
    for p, (prof, projs, props) in personas.items():
        others = [x for q, (_, ps, _) in personas.items() if q != p for x in ps]
        dev = []
        for i in range(args.dev_per_persona):
            kind = rng.choices([m[0] for m in mix], weights=[m[1] for m in mix])[0]
            if kind == "relevant":
                job = G.make_relevant_job(p, prof, projs, props, stats, rng, title_pool=titles_by_cat.get(G.CATEGORY_OF_PERSONA[p]))
            elif kind == "vague":
                job = G.make_relevant_job(p, prof, projs, props, stats, rng, vague=True)
            elif kind == "low_budget":
                job = G.make_relevant_job(p, prof, projs, props, stats, rng, low_budget=True)
            elif kind == "offdomain":
                job = G.make_offdomain_job(p, stats, rng, others)
            elif kind == "scam":
                job = G.make_scam_job(p, rng)
            else:
                job = G.add_injection(G.make_relevant_job(p, prof, projs, props, stats, rng), rng)
            job, cl = G.finalize(job, rng, (t0 + timedelta(hours=i)).isoformat())
            clients[cl["id"]] = cl
            dev.append(job)
        (DEV / f"dev_{p}.jsonl").write_text("\n".join(json.dumps(j) for j in dev) + "\n")
        print(p, {k: sum(j["gold"]["job_type"] == k for j in dev) for k in
                  ("standard", "multi_req", "vague", "low_budget", "off_domain", "scam", "injection")})

    # 3) live stream: released by GigSim over time, includes duplicates, scams, injections (no gold exposed)
    stream = []
    for i in range(args.stream):
        p = rng.choice(list(personas))
        prof, projs, props = personas[p]
        r = rng.random()
        if r < .45:
            job = G.make_relevant_job(p, prof, projs, props, stats, rng)
        elif r < .65:
            job = G.make_offdomain_job(p, stats, rng)
        elif r < .78:
            job = G.make_scam_job(p, rng)
        else:
            job = G.add_injection(G.make_relevant_job(p, prof, projs, props, stats, rng), rng)
        job, cl = G.finalize(job, rng, (datetime(2026, 11, 1) + timedelta(minutes=37 * i)).isoformat())
        clients[cl["id"]] = cl
        stream.append(job)
        if rng.random() < .08:  # re-post duplicate (same content, new id) to exercise dedup
            dup = dict(job, id=job["id"] + "d", posted_at=(datetime(2026, 11, 1) + timedelta(minutes=37 * i + 5)).isoformat())
            stream.append(dup)
    (PROC / "stream_jobs.jsonl").write_text("\n".join(json.dumps(j) for j in stream) + "\n")
    (PROC / "clients.jsonl").write_text("\n".join(json.dumps(c) for c in clients.values()) + "\n")
    # committed copy of clients referenced by the dev set so evals are reproducible from the repo alone
    dev_clients = {json.loads(l)["client_id"] for p in personas for l in (DEV / f"dev_{p}.jsonl").read_text().splitlines()}
    (DEV / "dev_clients.jsonl").write_text("\n".join(json.dumps(clients[c]) for c in dev_clients) + "\n")
    print(f"pricing stats: {stats_source}; kaggle rows: {len(rows)}; historical={len(hist)} stream={len(stream)} clients={len(clients)}")


if __name__ == "__main__":
    main()
