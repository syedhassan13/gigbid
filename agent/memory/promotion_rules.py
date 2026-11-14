"""Explicit promotion rules (R7). Raw edits/outcomes are OBSERVATIONS; only patterns that
pass a rule become long-term memory the writer reads.

Style rule:   an edit pattern seen in >= memory.style_promotion_min_occurrences distinct approved edits.
Outcome rule: a (category, arm) cell with >= memory.outcome_promotion_min_samples resolved proposals;
              stores reply rate + hire rate; recomputed on every new outcome.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import time

from agent.settings import config

PHRASE_MIN = 2


def _sents(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def edit_patterns(before: str, after: str) -> list[dict]:
    """Diff an AI draft against the user's edit and name the patterns."""
    pats = []
    b, a = _sents(before), _sents(after)
    if b and a and b[0] not in after:
        pats.append({"pattern": "cut_first_sentence", "rule": "Do not open with a preamble; start with the client's problem.", "example": b[0][:160]})
    if len(after.split()) < 0.8 * len(before.split()):
        pats.append({"pattern": "shorter", "rule": "Keep proposals ~20% shorter than the default length.", "example": f"{len(before.split())}->{len(after.split())} words"})
    if after.count("?") > before.count("?"):
        pats.append({"pattern": "added_question", "rule": "End with one specific question about the client's project.", "example": ""})
    bl, al = before.lower(), after.lower()
    for w in ("passionate", "hard-working", "hardworking", "perfectly", "high quality", "dear", "kindly", "expert", "excited"):
        if re.search(rf"\b{re.escape(w)}\b", bl) and not re.search(rf"\b{re.escape(w)}\b", al):
            pats.append({"pattern": f"never_say:{w}", "rule": f"Never say \"{w}\".", "example": w})
    sm = difflib.SequenceMatcher(None, before, after)
    pats_diff = round(1 - sm.ratio(), 3)
    for p in pats:
        p["edit_distance"] = pats_diff
    return pats


def observe_edit(store, user: str, before: str, after: str, thread_id: str) -> list[str]:
    """Record edit observations; promote patterns that recur. Returns promoted pattern names."""
    if not store or before.strip() == after.strip():
        return []
    promoted = []
    need = config()["memory"]["style_promotion_min_occurrences"]
    for p in edit_patterns(before, after):
        key = hashlib.md5(p["pattern"].encode()).hexdigest()[:12]
        cur = store.get(("style_candidates", user), key)
        threads = set((cur.value.get("threads") if cur else []) or []) | {thread_id}
        store.put(("style_candidates", user), key, {**p, "threads": sorted(threads), "count": len(threads), "updated": time.time()})
        if len(threads) >= need and not store.get(("style", user), key):
            store.put(("style", user), key, {"pattern": p["pattern"], "rule": p["rule"], "evidence_threads": sorted(threads),
                                            "promoted_by": f"seen in {len(threads)} approved edits (>= {need})", "promoted_at": time.time()})
            promoted.append(p["pattern"])
    return promoted


def observe_outcome(store, user: str, proposal_id: str, category: str, arm: str | None, status: str) -> dict | None:
    """status in viewed|replied|interview|hired|lost. Promote (category, arm) stats once enough samples resolve."""
    if not store or status not in ("replied", "interview", "hired", "lost"):
        return None
    store.put(("outcome_obs", user), proposal_id, {"category": category, "arm": arm or "-", "status": status, "ts": time.time()})
    obs = [i.value for i in store.search(("outcome_obs", user), limit=1000) if i.value["category"] == category and i.value["arm"] == (arm or "-")]
    n = len(obs)
    if n < config()["memory"]["outcome_promotion_min_samples"]:
        return None
    replied = sum(o["status"] in ("replied", "interview", "hired") for o in obs)
    hired = sum(o["status"] == "hired" for o in obs)
    val = {"category": category, "arm": arm or "-", "n": n, "reply_rate": round(replied / n, 3), "hire_rate": round(hired / n, 3),
           "promoted_by": f"n={n} >= {config()['memory']['outcome_promotion_min_samples']}", "updated": time.time()}
    store.put(("outcome", user), f"{category}:{arm or '-'}", val)
    return val
