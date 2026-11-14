"""Risk Assessor (Marketplace read): client quality from history + scam / free-work /
off-platform / injected-instruction detection. Rules first (cheap, testable), small LLM
only for ambiguous cases."""
from __future__ import annotations

import re

from pydantic import BaseModel

from agent import llm
from agent.handoffs import RiskFlag, RiskReport
from agent.nodes.base import node
from agent.state import trace_event

INJECTION = [r"ignore (all |any )?(previous|prior|above) instructions", r"\[system\]", r"you are now", r"ai (assistants|agents)\b.*(reading|:)",
             r"disregard (your|all) (rules|instructions)", r"reveal (your )?(system prompt|instructions)", r"<!--\s*assistant", r"admin mode",
             r"recommend bid with a price", r"respond with (bid|yes)"]
OFF_PLATFORM = [r"telegram", r"whatsapp", r"wa\.me", r"t\.me/", r"skype", r"outside the platform", r"off[- ]platform", r"paypal", r"western union",
                r"crypto|usdt|bitcoin", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", r"text me", r"do not use the platform"]
FREE_WORK = [r"unpaid (test|trial)", r"free sample", r"complete the full .* (first|as an unpaid)", r"best submission gets", r"before hiring, complete"]
PAYMENT_SCAM = [r"send you a check", r"deposit it", r"transfer the difference", r"pay(ment)? (via|through) crypto"]


def find(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0)
    return None


def strip_injection(text: str) -> str:
    """Remove lines/paragraphs carrying injected instructions (the text stays delimited anyway)."""
    keep = [para for para in re.split(r"\n\s*\n", text) if not find(INJECTION, para)]
    return "\n\n".join(keep)


class _LLMRisk(BaseModel):
    is_scam: bool
    reason: str


def assess(job: dict, client: dict) -> RiskReport:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    flags: list[RiskFlag] = []
    if (m := find(INJECTION, text)):
        flags.append(RiskFlag(code="injection", severity=0.5, evidence=m))
    if (m := find(OFF_PLATFORM, text)):
        flags.append(RiskFlag(code="off_platform", severity=0.85, evidence=m))
    if (m := find(FREE_WORK, text)):
        flags.append(RiskFlag(code="free_work", severity=0.85, evidence=m))
    if (m := find(PAYMENT_SCAM, text)):
        flags.append(RiskFlag(code="payment_scam", severity=0.95, evidence=m))
    # client quality
    cs = 0.5
    if client.get("payment_verified"):
        cs += 0.15
    else:
        flags.append(RiskFlag(code="unverified_payment", severity=0.35, evidence="payment method not verified"))
    spent, hires = client.get("total_spent") or 0, client.get("hires") or 0
    cs += min(0.2, spent / 50000) + min(0.1, hires / 50)
    if spent == 0 and hires == 0:
        flags.append(RiskFlag(code="no_history", severity=0.3, evidence="no spend, no hires"))
        cs -= 0.15
    if client.get("avg_rating") is not None and client["avg_rating"] < 4.0:
        flags.append(RiskFlag(code="low_rating", severity=0.3, evidence=f"rating {client['avg_rating']}"))
        cs -= 0.1
    cs = max(0.0, min(1.0, cs))
    scam_codes = {"off_platform", "free_work", "payment_scam"}
    hard = max([f.severity for f in flags if f.code in scam_codes] or [0])
    soft = sum(f.severity for f in flags if f.code in ("unverified_payment", "no_history", "low_rating")) / 3
    risk = max(hard, 0.6 * soft + 0.4 * (1 - cs))
    is_scam = hard >= 0.8
    if not is_scam and 0.3 <= risk < 0.6:  # ambiguous: ask the cheap model
        out = llm.complete_json("risk", llm.prompt("risk"), llm.untrusted("JOB POST", text[:3000]), _LLMRisk, max_tokens=200)
        if out and out.is_scam:
            is_scam, risk = True, max(risk, 0.75)
            flags.append(RiskFlag(code="off_platform", severity=0.75, evidence=f"LLM: {out.reason[:120]}"))
    summary = "; ".join(f"{f.code} ({f.evidence[:40]})" for f in flags) or "no risk flags"
    return RiskReport(job_id=job["id"], client_score=round(cs, 3), risk_score=round(risk, 3), is_scam=is_scam,
                      injection_detected=any(f.code == "injection" for f in flags), flags=flags, summary=summary)


@node("risk")
async def risk(state: dict, cfg: dict, store) -> dict:
    rep = assess(state["job"], state.get("client") or {})
    return {"analyses": {"risk": rep.model_dump()},
            "trace": trace_event("risk", "observation", risk_score=rep.risk_score, is_scam=rep.is_scam, flags=[f.code for f in rep.flags])}
