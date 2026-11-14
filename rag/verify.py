"""Claim verification (B3 / R5): split a draft into claims, ground each against
portfolio evidence, label supported / partial / unsupported, and remove or
rewrite unsupported claims BEFORE the Critic sees the draft.

Support score per (claim, evidence) = 0.45 * key-term coverage + 0.55 * cosine,
with a hard rule: any number in a claim (metric, count, years) must literally
appear in some evidence, otherwise the claim is at most "partial" and the
number is stripped.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from agent import llm
from rag.index.models import embed, tokenize
from rag.pipeline import Evidence
from rag.retriever import retrieve

CLAIM_VERBS = re.compile(r"(?i)\b(i|i've|i have|i'm|my|we)\b.*\b(built|shipped|delivered|designed|developed|created|led|worked|"
                         r"implemented|deployed|reduced|increased|cut|raised|improved|saved|automated|migrated|helped|have|"
                         r"experience|solved|years?)\b")
NUM = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|k\b|x\b)?")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
GENERIC_SKILL_WORDS = {"experience", "project", "client", "built", "work", "worked", "years", "team", "system", "using", "similar", "last", "year"}


@dataclass
class ClaimVerdict:
    claim: str
    label: str            # supported | partial | unsupported
    score: float
    evidence_ids: list[str]
    unsupported_numbers: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT.split(text.strip()) if s.strip()]


def is_claim(sentence: str) -> bool:
    if sentence.endswith("?"):
        return False
    if re.match(r"(?i)^(i would|i will|i'd|i can|i plan|my plan|first,|then|next,)", sentence):
        return bool(re.search(r"(?i)\b(built|shipped|delivered|for a .* client)\b", sentence))
    return bool(CLAIM_VERBS.search(sentence)) or bool(re.search(r"(?i)\bfor an? [a-z -]+ (client|company|startup|chain|lab|agency|business)\b", sentence))


def _terms(s: str) -> set[str]:
    return {t for t in tokenize(s) if len(t) > 2 and t not in GENERIC_SKILL_WORDS and not t.isdigit()}


def _numbers(s: str) -> list[str]:
    return [n.strip() for n in NUM.findall(s) if re.search(r"\d", n)]


def verify_claims(text: str, persona: str, evidence: list[Evidence] | None = None, *, use_llm: bool = True) -> list[ClaimVerdict]:
    sents = [s for s in split_sentences(text) if is_claim(s)]
    if not sents:
        return []
    evidence = list(evidence or [])
    pool: dict[str, Evidence] = {e.chunk_id: e for e in evidence}
    for s in sents:  # independent re-retrieval per claim: the writer may cite the wrong item
        for e in retrieve(s, persona, k=4, variant="v2_hybrid").evidence:
            pool.setdefault(e.chunk_id, e)
    ev = list(pool.values())
    if not ev:
        return [ClaimVerdict(s, "unsupported", 0.0, [], _numbers(s)) for s in sents]
    em = embed([e.text for e in ev])
    cm = embed(sents)
    verdicts = []
    for i, s in enumerate(sents):
        terms = _terms(s)
        best, best_ids = 0.0, []
        scored = []
        for j, e in enumerate(ev):
            et = _terms(e.text + " " + e.title)
            cov = len(terms & et) / len(terms) if terms else 0.5
            score = 0.45 * cov + 0.55 * float(cm[i] @ em[j])
            scored.append((score, e.doc_id))
        scored.sort(reverse=True)
        best = scored[0][0]
        best_ids = list(dict.fromkeys(d for _, d in scored[:3]))
        all_ev_text = " ".join(e.text for e in ev)
        bad_nums = [n for n in _numbers(s) if n.replace(" ", "") not in all_ev_text.replace(" ", "")]
        label = "supported" if best >= 0.62 else ("partial" if best >= 0.45 else "unsupported")
        if bad_nums and label == "supported":
            label = "partial"
        verdicts.append(ClaimVerdict(s, label, round(best, 3), best_ids, bad_nums))
    if use_llm:
        _llm_recheck(verdicts, ev)
    return verdicts


def _llm_recheck(verdicts: list[ClaimVerdict], ev: list[Evidence]) -> None:
    """Optional NLI pass for borderline claims (partial). Only downgrades/upgrades by one level."""
    from pydantic import BaseModel

    class NLI(BaseModel):
        label: str  # supported | partial | unsupported

    by_id = {e.doc_id: e for e in ev}
    for v in verdicts:
        if v.label != "partial":
            continue
        ctx = "\n---\n".join(by_id[d].text[:700] for d in v.evidence_ids if d in by_id)
        out = llm.complete_json("verifier", llm.prompt("verifier"), f"CLAIM: {v.claim}\n\nEVIDENCE:\n{ctx}", NLI, max_tokens=200)
        if out and out.label in ("supported", "partial", "unsupported") and not v.unsupported_numbers:
            v.label = out.label


def apply_fixes(text: str, verdicts: list[ClaimVerdict]) -> str:
    """Remove unsupported claims; strip unsupported numbers from partial claims."""
    out = text
    for v in verdicts:
        if v.label == "unsupported":
            out = out.replace(v.claim, "").replace("  ", " ")
        elif v.unsupported_numbers:
            fixed = v.claim
            for n in v.unsupported_numbers:
                fixed = re.sub(rf"\s*(by|of|over|about|around)?\s*{re.escape(n)}\s*(%|percent)?", "", fixed)
            out = out.replace(v.claim, fixed)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def report(verdicts: list[ClaimVerdict]) -> dict:
    n = len(verdicts)
    return {"claims": n, "supported": sum(v.label == "supported" for v in verdicts),
            "partial": sum(v.label == "partial" for v in verdicts),
            "unsupported": sum(v.label == "unsupported" for v in verdicts),
            "verdicts": [v.to_dict() for v in verdicts]}
