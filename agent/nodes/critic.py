"""Claim verification node (B3) and Critic (Portfolio read).

verifier: split the draft into claims, ground each against evidence, remove/rewrite
          unsupported ones BEFORE the critic sees the draft; record before/after counts.
critic:   grounding, personalisation and length checks (+ LLM rubric when available);
          sends the draft back to the writer with reasons, at most critic.max_revisions times.
"""
from __future__ import annotations

import re

from agent import llm
from agent.handoffs import Critique
from agent.nodes.base import node
from agent.settings import config, policy_rules
from agent.state import trace_event
from rag.index.models import tokenize
from rag.verify import apply_fixes, report, verify_claims


@node("verifier")
async def verifier(state: dict, cfg: dict, store) -> dict:
    d = dict(state["draft"])
    v = verify_claims(d["cover_letter"], state["persona"])
    before = report(v)
    fixed = apply_fixes(d["cover_letter"], v)
    after = report(verify_claims(fixed, state["persona"], use_llm=False)) if fixed != d["cover_letter"] else before
    answers = [apply_fixes(a, verify_claims(a, state["persona"], use_llm=False)) for a in d.get("screening_answers", [])]
    d["cover_letter"], d["screening_answers"] = fixed, answers
    ver = {"before": {k: before[k] for k in ("claims", "supported", "partial", "unsupported")},
           "after": {k: after[k] for k in ("claims", "supported", "partial", "unsupported")}, "verdicts": after["verdicts"]}
    return {"draft": d, "verification": ver,
            "trace": trace_event("verifier", "observation", unsupported_before=before["unsupported"], unsupported_after=after["unsupported"])}


GENERIC = [b.lower() for r in policy_rules()["rules"] if r["kind"] == "opening_check" for b in r["banned_openings"]]


def rule_critique(job: dict, draft: dict, verification: dict) -> Critique:
    c = config()["critic"]
    text = draft["cover_letter"]
    issues = []
    words = len(text.split())
    length_ok = c["min_words"] <= words <= c["max_words"]
    if not length_ok:
        issues.append(f"length {words} words; target {c['min_words']}-{c['max_words']} ({'too long' if words > c['max_words'] else 'too short'})")
    first = re.split(r"(?<=[.!?])\s", text.strip(), 1)[0].lower()
    job_terms = set(tokenize(job["title"] + " " + job["description"])) - {"need", "want", "looking", "experience", "project"}
    overlap = len(job_terms & set(tokenize(text)))
    personal = overlap >= 4 and not any(first.startswith(g) for g in GENERIC)
    if not personal:
        issues.append("not personalised: opening is generic or the letter reuses few of the client's own terms")
    unsupported = verification.get("after", {}).get("unsupported", 0)
    grounding = unsupported == 0 and bool(draft.get("citations"))
    if unsupported:
        issues.append(f"{unsupported} unsupported claim(s) remain")
    if not draft.get("citations"):
        issues.append("no claim cites portfolio evidence")
    if len(draft.get("screening_answers", [])) < len(job.get("screening_questions", [])):
        issues.append("missing screening answers")
    score = 10 - 2.5 * (not length_ok) - 3 * (not personal) - 3 * (not grounding)
    return Critique(passed=not issues, issues=issues, grounding_ok=grounding, personalisation_ok=personal, length_ok=length_ok, score=max(0, score))


@node("critic")
async def critic(state: dict, cfg: dict, store) -> dict:
    crit = rule_critique(state["job"], state["draft"], state.get("verification", {}))
    if crit.passed:  # rules pass -> ask the strong model for a rubric check (if available)
        out = llm.complete_json("critic", llm.prompt("critic"),
                                llm.untrusted("JOB POST", state["job"]["description"][:2500]) + f"\n\nDRAFT:\n{state['draft']['cover_letter']}",
                                Critique, max_tokens=500)
        if out and not out.passed and out.issues:
            crit = Critique(passed=False, issues=out.issues[:4], grounding_ok=crit.grounding_ok, personalisation_ok=out.personalisation_ok,
                            length_ok=crit.length_ok, score=out.score)
    return {"critiques": [crit.model_dump()], "trace": trace_event("critic", "critique", passed=crit.passed, issues=crit.issues, score=crit.score)}


def after_critic(state: dict) -> str:
    if state.get("status") == "needs_attention":
        return "end"
    last = state["critiques"][-1]
    if not last["passed"] and (state.get("revisions") or 0) < config()["critic"]["max_revisions"]:
        return "revise"
    return "compliance"
