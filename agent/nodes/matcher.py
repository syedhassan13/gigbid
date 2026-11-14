"""Fit Matcher (Portfolio read): map every requirement to portfolio evidence via the
Portfolio MCP server's search_evidence tool; produce a fit score with reasons."""
from __future__ import annotations

import asyncio
import json
from functools import lru_cache

from agent.handoffs import FitReport, RequirementMatch
from agent.mcp_client import call_tool
from agent.nodes.base import cfg_val, node
from agent.nodes.risk import strip_injection
from agent.settings import ROOT
from agent.state import trace_event
from rag.pipeline import extract_requirements


@lru_cache
def _prevalence_table() -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in (ROOT / "data" / "personas").glob("*/profile.json"):
        for s in json.loads(p.read_text()).get("skills", []):
            counts[s.lower()] = counts.get(s.lower(), 0) + 1
    return counts


def _skill_prevalence(req: str) -> int:
    return _prevalence_table().get(req.lower().strip(), 1)


async def match(job: dict, persona: str, requirements: list[str] | None = None) -> FitReport:
    clean = {**job, "description": strip_injection(job.get("description", ""))}
    reqs = requirements or extract_requirements(clean)

    async def one(r: str) -> RequirementMatch:
        res = await call_tool("matcher", "portfolio", "search_evidence", {"requirement": r, "k": 3, "filters": {"persona": persona}})
        items = res.get("items", [])
        best = items[0]["score"] if items else 0.0
        return RequirementMatch(requirement=r, evidence_ids=[i["id"] for i in items], best_score=best, covered=not res.get("weak", True),
                                note=items[0]["title"] if items else "no evidence")
    matches = list(await asyncio.gather(*[one(r) for r in reqs]))
    # specificity weighting: a skill listed by many persona profiles (SQL, Python) proves less fit than a
    # specific one (Looker, NLP); failure analysis showed generic overlap drove off-domain wrong bids.
    w = [1.0 / max(1, _skill_prevalence(m.requirement)) for m in matches]
    cov = sum(wi for wi, m in zip(w, matches) if m.covered) / sum(w) if matches else 0.0
    mean = sum(m.best_score for m in matches) / len(matches) if matches else 0.0
    fit = round(0.7 * cov + 0.3 * mean, 3)
    reasons = [f"{sum(m.covered for m in matches)}/{len(matches)} requirements backed by portfolio evidence"]
    reasons += [f"'{m.requirement}' ← {m.evidence_ids[0]}" for m in matches if m.covered][:4]
    return FitReport(job_id=job["id"], fit_score=fit, matches=matches, missing=[m.requirement for m in matches if not m.covered], reasons=reasons)


@node("matcher")
async def matcher(state: dict, cfg: dict, store) -> dict:
    rep = await match(state["job"], cfg_val(cfg, "persona") or state["persona"])
    return {"analyses": {"fit": rep.model_dump()},
            "trace": trace_event("matcher", "tool_result", tool="portfolio.search_evidence", n_requirements=len(rep.matches),
                                 fit=rep.fit_score, missing=rep.missing)}
