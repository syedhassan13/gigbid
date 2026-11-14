"""Proposal Writer (Portfolio read): cover letter + screening answers in which every
claim cites portfolio evidence. Reads promoted style + outcome memory. X2: two
opening strategies (arms) assigned deterministically by job id."""
from __future__ import annotations

import hashlib
import re

from agent import llm
from agent.handoffs import Citation, ProposalDraft
from agent.mcp_client import call_tool
from agent.memory.store import outcome_memory, style_rules
from agent.nodes.base import cfg_val, node
from agent.nodes.risk import strip_injection
from agent.settings import config, policy_rules
from agent.state import trace_event


def experiment_arm(job_id: str) -> str | None:
    ex = config()["experiment"]
    if not ex["enabled"]:
        return None
    return "A" if int(hashlib.md5(job_id.encode()).hexdigest(), 16) % 2 == 0 else "B"


def _section(text: str, heading: str) -> str:
    m = re.search(rf"## {heading}\n(.+?)(?:\n## |\Z)", text, re.S)
    return m.group(1).strip() if m else ""


async def gather_evidence(fit: dict, persona: str) -> list[dict]:
    """Best evidence per covered requirement, de-duplicated by project, with full case-study text."""
    out, seen_proj = [], set()
    for m in fit.get("matches", []):
        if not m["covered"]:
            continue
        for eid in m["evidence_ids"][:2]:
            try:
                cs = await call_tool("writer", "portfolio", "get_case_study", {"id": eid, "persona": persona})
            except Exception:
                continue
            proj = eid.split(":", 1)[1] if ":" in eid else eid
            key = next((r for r in cs.get("related", []) if r.startswith("case:")), eid)
            if key in seen_proj:
                continue
            seen_proj.add(key)
            out.append({"id": eid, "requirement": m["requirement"], "title": cs["title"], "type": cs["type"], "text": cs["text"][:1500],
                        "industry": cs.get("client_industry"), "related": cs.get("related", []), "project": proj})
            break
    return out


def heuristic_draft(job: dict, spec: dict, evidence: list[dict], price: dict, arm: str | None, styles: list[dict],
                    critique: dict | None, revision: int) -> ProposalDraft:
    title = job["title"]
    reqs = spec.get("requirements", [])[:3]
    cites: list[Citation] = []
    proof_sents = []
    for ev in evidence[:2]:
        built = _section(ev["text"], "What I built")
        outcome = _section(ev["text"], "Outcome")
        if ev["type"] == "case_study" and built:
            first = re.split(r"(?<=\.)\s", built)[0].replace("I designed and delivered ", "")
            s = f"For a client in {ev['industry']} I delivered {first.rstrip('.')}"
            if outcome:
                s += f"; {re.split(r'(?<=\.)\s', outcome)[0].replace('Within the first months the system ', 'it ').rstrip('.')}"
            s += "."
        elif ev["type"] == "repo_readme":
            s = f"I built and maintain a similar service ({ev['title']}) using {ev['requirement']}."
        elif ev["type"] == "proposal":
            s = f"I have shipped work on '{ev['title'].replace('Proposal for job: ', '')}' before, covering {ev['requirement']}."
        else:
            s = f"My portfolio item '{ev['title']}' covers {ev['requirement']}."
        proof_sents.append(s)
        cites.append(Citation(sentence=s, evidence_ids=[ev["id"]] + [r for r in ev["related"] if r.startswith(("case:", "repo:"))][:1]))
    problem = re.search(r"(?i)our problem:\s*([^.]+)", job.get("description", ""))
    need = problem.group(1) if problem else (reqs[0] if reqs else title)
    if arm == "B":
        opening = f"How are you handling {need.strip()} today, and what has already been tried?"
    else:
        opening = f"You need {title[0].lower() + title[1:]}" + (f" with {', '.join(reqs[:2])}" if reqs else "") + "."
    plan = (f"My plan: a short call to confirm scope, a working first milestone covering {reqs[0] if reqs else 'the core flow'}, "
            f"then the hardened version with tests and a handover note.")
    if price.get("unit") == "hourly":
        p = f"My rate for this is ${price['amount']:.0f}/hour."
    else:
        p = f"I can deliver this for ${price['amount']:.0f} fixed."
    closing = "Which part matters most to you in the first two weeks?" if arm != "B" else "Happy to walk through how I would apply that here."
    parts = [opening] + proof_sents + [plan, p, closing]
    if any(s.get("pattern") == "shorter" for s in styles) or (critique and any("long" in i for i in critique.get("issues", []))):
        parts = [opening] + proof_sents[:1] + [p, closing]
    if not proof_sents:
        parts = [opening, f"I have not done this exact project, so I won't overstate it; I would approach it by first validating {need.strip()} with you.", plan, p, closing]
    letter = " ".join(parts)
    answers = []
    for q in spec.get("screening_questions", []):
        if proof_sents and re.search(r"(?i)similar project", q):
            answers.append(proof_sents[0])
        elif re.search(r"(?i)first week|approach", q):
            answers.append(plan)
        elif re.search(r"(?i)risk", q):
            answers.append(f"The riskiest part is {(reqs[-1] if reqs else 'unclear scope')}; I would de-risk it in the first milestone.")
        else:
            answers.append("I can commit 20-30 hours per week and overlap with your working hours.")
    return ProposalDraft(cover_letter=letter, screening_answers=answers, citations=cites, variant=arm, revision=revision)


@node("writer")
async def writer(state: dict, cfg: dict, store) -> dict:
    job = {**state["job"], "description": strip_injection(state["job"]["description"])}
    spec, fit, price = state["analyses"]["job_spec"], state["analyses"]["fit"], state["price"]
    persona, user = state["persona"], state.get("user_id", "demo")
    evidence = await gather_evidence(fit, persona)
    arm = (state.get("draft") or {}).get("variant") or experiment_arm(job["id"])
    styles, outcomes = style_rules(store, user), outcome_memory(store, user)
    critique = state["critiques"][-1] if state.get("critiques") else None
    revision = (state.get("revisions") or 0) + (1 if critique else 0)
    ev_block = "\n\n".join(f"[{e['id']}] ({e['type']}, industry: {e['industry']}) proves '{e['requirement']}':\n{e['text'][:900]}" for e in evidence) or "(no evidence)"
    arm_text = {"A": "Open with the single most relevant proof (project + measurable outcome).",
                "B": "Open with one diagnostic question about the client's problem, then the proof."}.get(arm or "", "")
    user_msg = (llm.untrusted("JOB POST", f"{job['title']}\n\n{job['description']}") +
                f"\n\nJOB SPEC: {spec}\n\nPRICE: {price['amount']} ({price['unit']})\n\nPORTFOLIO EVIDENCE (cite ids):\n{ev_block}\n\n"
                f"OPENING STRATEGY: {arm_text}\nSTYLE RULES (learned from the user's edits): {[s['rule'] for s in styles]}\n"
                f"OUTCOME MEMORY: {outcomes[:5]}\nREQUIRED STATEMENTS: {policy_rules().get('required_statements', [])}\n"
                + (f"\nCRITIC FEEDBACK TO FIX: {critique['issues']}\nPREVIOUS DRAFT:\n{state['draft']['cover_letter']}" if critique else ""))
    out = llm.complete_json("writer", llm.prompt("writer"), user_msg, ProposalDraft, max_tokens=1600, temperature=0.4)
    if out:
        out.variant, out.revision = arm, revision
        draft = out
    else:
        draft = heuristic_draft(job, spec, evidence, price, arm, styles, critique, revision)
    return {"draft": draft.model_dump(), "revisions": revision,
            "trace": trace_event("writer", "draft", revision=revision, arm=arm, words=len(draft.cover_letter.split()),
                                 evidence=[e["id"] for e in evidence], llm=bool(out))}
