"""Compliance Guard (no MCP access): enforce the policy pack (data/policy_pack/rules.yaml).
Removes contact details, off-platform asks, guarantees and invented claims; adds required
statements; blocks with a reason shown in the UI when a violation cannot be fixed."""
from __future__ import annotations

import re

from agent.handoffs import ComplianceVerdict
from agent.nodes.base import node
from agent.settings import policy_rules
from agent.state import trace_event


def _sentences(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def enforce(text: str, verification: dict | None = None, add_required: bool = True) -> ComplianceVerdict:
    """add_required: append policy-mandated statements (proposal cover letters only, not answers or messages)."""
    rules = policy_rules()
    fixes: list[str] = []
    out = text
    for r in rules["rules"]:
        k = r["kind"]
        if k == "regex_redact":
            new = re.sub(r["pattern"], r["replacement"], out)
            if new != out:
                fixes.append(f"{r['id']}: removed contact details")
                out = new
        elif k == "phrase_redact":
            kept = [s for s in _sentences(out) if not any(p in s.lower() for p in r["phrases"])]
            if len(kept) != len(_sentences(out)):
                fixes.append(f"{r['id']}: removed off-platform wording")
                out = " ".join(kept)
        elif k == "phrase_rewrite":
            new_s = []
            for s in _sentences(out):
                if any(p in s.lower() for p in r["phrases"]):
                    fixes.append(f"{r['id']}: removed guarantee \"{s[:60]}\"")
                    continue
                new_s.append(s)
            out = " ".join(new_s)
        elif k == "opening_check":
            ss = _sentences(out)
            if ss and any(ss[0].lower().startswith(b) for b in r["banned_openings"]):
                fixes.append(f"{r['id']}: dropped generic opening")
                out = " ".join(ss[1:])
        elif k == "length":
            words = out.split()
            if len(words) > r["max_words"]:
                ss, acc = _sentences(out), []
                for s in ss:
                    if len(" ".join(acc + [s]).split()) > r["max_words"]:
                        break
                    acc.append(s)
                out = " ".join(acc)
                fixes.append(f"{r['id']}: trimmed to {r['max_words']} words")
    for stmt in (rules.get("required_statements", []) or []) if add_required else []:
        if stmt.lower() not in out.lower():
            out = out.rstrip() + "\n\n" + stmt
            fixes.append(f"required statement added: \"{stmt}\"")
    blocked = None
    # P2: invented claims - verification must have removed every unsupported claim
    if verification and verification.get("after", {}).get("unsupported", 0) > 0:
        blocked = f"P2 fabricated experience: {verification['after']['unsupported']} unsupported claim(s) remain"
    # unfixable residue check
    for r in rules["rules"]:
        if r["kind"] == "regex_redact" and re.search(r["pattern"], out):
            blocked = f"{r['policy']}: contact details remain after redaction"
    if len(out.split()) < next((r["min_words"] for r in rules["rules"] if r["kind"] == "length"), 0) // 2:
        blocked = blocked or "draft too short after removing non-compliant content"
    return ComplianceVerdict(allowed=blocked is None, blocked_reason=blocked, fixes_applied=fixes, text=out.strip())


@node("compliance")
async def compliance(state: dict, cfg: dict, store) -> dict:
    d = dict(state["draft"])
    src = (state.get("approval") or {}).get("edited_text") if (state.get("approval") or {}).get("decision") == "edit" else d["cover_letter"]
    v = enforce(src, state.get("verification") if src == d["cover_letter"] else None)
    answers = [enforce(a, add_required=False).text for a in d.get("screening_answers", [])]
    d["cover_letter"], d["screening_answers"] = v.text, answers
    status = "awaiting_approval" if v.allowed else "needs_attention"
    return {"draft": d, "compliance": v.model_dump(), "status": status, "approval": {},
            "error": v.blocked_reason or "", "trace": trace_event("compliance", "verdict", allowed=v.allowed, fixes=v.fixes_applied, blocked=v.blocked_reason)}
