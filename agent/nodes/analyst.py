"""Job Analyst (no MCP access): job post -> structured JobSpec."""
from __future__ import annotations

import re

from agent import llm
from agent.handoffs import JobSpec
from agent.nodes.base import node
from agent.state import trace_event
from rag.pipeline import extract_requirements

HIDDEN = [(r"non-technical|without me|hand ?over", "clear handover docs and training"), (r"slow|performance|speed", "performance budget"),
          (r"urgent|asap|quickly", "fast turnaround"), (r"trust|reliab", "reliability / monitoring"),
          (r"mobile", "mobile-first UX"), (r"scale|growing", "scalability")]


def heuristic_spec(job: dict) -> JobSpec:
    desc = job.get("description", "")
    deliv = []
    if re.search(r"(?i)deliverables:", desc):
        deliv = [m.strip(" -•") for m in re.split(r"(?i)deliverables:", desc, 1)[1].splitlines() if m.strip().startswith(("-", "•"))]
    timeline = (re.search(r"(?i)(\d+\s*(?:weeks?|days?|months?))", desc) or [None])[0]
    reqs = extract_requirements(job)
    vague = not re.search(r"(?i)requirements?:", desc) and not job.get("skills")
    return JobSpec(job_id=job["id"], title=job["title"], deliverables=deliv, requirements=reqs, budget_type=job.get("budget_type", "fixed"),
                   budget_min=job.get("budget_min"), budget_max=job.get("budget_max"), timeline=timeline,
                   screening_questions=job.get("screening_questions", []),
                   hidden_needs=[need for pat, need in HIDDEN if re.search(pat, desc, re.I)], category=job.get("category", "other"), vague=vague)


def analyse(job: dict) -> JobSpec:
    base = heuristic_spec(job)
    out = llm.complete_json("analyst", llm.prompt("analyst"), llm.untrusted("JOB POST", f"TITLE: {job['title']}\n\n{job['description']}"),
                            JobSpec, max_tokens=900)
    if out:
        out.job_id, out.title = job["id"], job["title"]
        out.budget_type, out.budget_min, out.budget_max = base.budget_type, base.budget_min, base.budget_max
        out.screening_questions = base.screening_questions or out.screening_questions
        out.category = base.category
        if not out.requirements:
            out.requirements = base.requirements
        return out
    return base


@node("analyst")
async def analyst(state: dict, cfg: dict, store) -> dict:
    spec = analyse(state["job"])
    return {"analyses": {"job_spec": spec.model_dump()},
            "trace": trace_event("analyst", "observation", requirements=spec.requirements, vague=spec.vague, hidden_needs=spec.hidden_needs)}
