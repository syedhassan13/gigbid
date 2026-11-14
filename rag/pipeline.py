"""Configurable retrieval pipeline. Every variant in rag/variants/ is just a
PipelineConfig, so `make eval-rag` re-runs the full comparison with one command.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from agent import llm
from agent.settings import config
from rag.index.models import DenseIndex, SparseIndex, rerank, rrf, tokenize
from rag.ingest.chunkers import CHUNKERS, Chunk
from rag.ingest.loaders import load_persona


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    chunking: str = "structure"     # fixed | structure | contextual | multivector
    query: str = "whole"            # whole | decompose | hyde | decompose_hyde
    retrieval: str = "dense"        # dense | hybrid
    rerank: bool = False
    outcome_boost: bool = False
    corrective: bool = False        # V8
    graph: bool = False             # V9
    candidates: int = 30


@dataclass
class Evidence:
    doc_id: str
    chunk_id: str
    type: str
    title: str
    text: str
    score: float
    project: str | None = None
    outcome: str | None = None
    requirement: str | None = None
    date: str | None = None
    source: str = "portfolio"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalResult:
    evidence: list[Evidence]
    per_requirement: dict[str, list[Evidence]] = field(default_factory=dict)
    weak_requirements: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    variant: str = ""


# ------------------------------------------------------------------ index cache
class PersonaIndex:
    def __init__(self, persona: str, chunking: str):
        self.persona = persona
        self.docs = load_persona(persona)
        self.chunks: list[Chunk] = CHUNKERS[chunking](self.docs)
        texts = [c.text for c in self.chunks]
        self.dense = DenseIndex(texts)
        self.sparse = SparseIndex(texts)
        # outcome stats per project (for outcome-aware ranking)
        self.project_outcomes: dict[str, dict[str, int]] = {}
        for d in self.docs:
            if d.type == "proposal" and d.meta.get("project"):
                po = self.project_outcomes.setdefault(d.meta["project"], {"won": 0, "replied": 0, "ignored": 0})
                po[d.meta["outcome"]] += 1
        # skill graph (V9): skill -> projects, project -> doc ids, project -> industry
        self.skill_projects: dict[str, set[str]] = {}
        self.project_docs: dict[str, list[int]] = {}
        self.project_industry: dict[str, str] = {}
        for i, c in enumerate(self.chunks):
            proj = c.meta.get("project")
            if not proj:
                continue
            self.project_docs.setdefault(proj, []).append(i)
            if c.meta.get("client_industry"):
                self.project_industry[proj] = c.meta["client_industry"]
            for s in c.meta.get("skills", []) or []:
                self.skill_projects.setdefault(s.lower(), set()).add(proj)
            if c.meta.get("kind") == "code":
                for t in tokenize(c.display):
                    self.skill_projects.setdefault(t, set()).add(proj)


@lru_cache(maxsize=16)
def get_index(persona: str, chunking: str) -> PersonaIndex:
    return PersonaIndex(persona, chunking)


def invalidate(persona: str | None = None) -> None:
    """Incremental re-index: embeddings are cached on disk by text hash, so a rebuild only embeds new chunks."""
    get_index.cache_clear()


# ------------------------------------------------------------------ query building
_REQ_LINE = re.compile(r"^\s*[-*•]\s*(.+)$", re.M)
_REQ_PREFIX = re.compile(r"(?i)^(strong experience with|must have shipped production work using|hands-on|comfortable working with|experience with|"
                         r"knowledge of|proficient in|expert in)\s+")
_REQ_SUFFIX = re.compile(r"(?i)\s+(is required|skills|required|experience)\.?$")


def extract_requirements(job: dict) -> list[str]:
    """Heuristic requirement decomposition (the Job Analyst's LLM JobSpec overrides this when available)."""
    reqs: list[str] = []
    desc = job.get("description", "")
    block = re.split(r"(?i)deliverables:", desc)[0]
    if re.search(r"(?i)requirements?:", block):
        block = re.split(r"(?i)requirements?:", block, maxsplit=1)[1]
        for m in _REQ_LINE.finditer(block):
            r = _REQ_SUFFIX.sub("", _REQ_PREFIX.sub("", m.group(1).strip())).strip(" .")
            if r:
                reqs.append(r)
    for s in job.get("skills") or []:
        if s.lower() not in {r.lower() for r in reqs}:
            reqs.append(s)
    if not reqs:  # vague post: use its sentences
        reqs = [s.strip() for s in re.split(r"(?<=[.!?])\s+", desc) if len(s.split()) > 4][:4]
    return reqs[:8]


def hyde_text(job: dict, persona: str) -> str:
    sys = llm.prompt("hyde")
    out = llm.complete_text("hyde", sys, llm.untrusted("JOB POST", f"{job.get('title', '')}\n{job.get('description', '')[:2000]}"), max_tokens=350)
    if out:
        return out
    # offline fallback: template expansion of the job into a first-person proposal
    reqs = extract_requirements(job)
    return (f"I recently delivered a project very similar to '{job.get('title', '')}'. I built it with {', '.join(reqs[:5])}. "
            f"The client had the same problem: {job.get('description', '')[:300]}")


def job_query(job: dict | str) -> dict:
    return {"title": "", "description": job, "skills": []} if isinstance(job, str) else job


# ------------------------------------------------------------------ core retrieval
def _search(ix: PersonaIndex, cfg: PipelineConfig, query: str, n: int) -> list[tuple[int, float]]:
    dense = ix.dense.search(query, n)
    if cfg.retrieval == "hybrid":
        return rrf([dense, ix.sparse.search(query, n)])[:n]
    return dense


def _graph_candidates(ix: PersonaIndex, query: str, industry: str | None) -> list[tuple[int, float]]:
    toks = set(tokenize(query))
    scores: dict[str, float] = {}
    for skill, projs in ix.skill_projects.items():
        st = set(tokenize(skill))
        if st and st <= toks:
            for p in projs:
                scores[p] = scores.get(p, 0) + 1.0 / len(projs)
    if industry:
        for p in scores:
            if ix.project_industry.get(p) == industry:
                scores[p] += 1.0
    out = []
    for p, s in sorted(scores.items(), key=lambda x: -x[1])[:6]:
        for i in ix.project_docs.get(p, []):
            out.append((i, s))
    return out


def _outcome_factor(ix: PersonaIndex, c: Chunk) -> float:
    if c.meta.get("type") == "proposal":
        return {"won": 1.35, "replied": 1.15, "ignored": 0.8}.get(c.meta.get("outcome"), 1.0)
    po = ix.project_outcomes.get(c.meta.get("project") or "", None)
    if po:
        tot = sum(po.values())
        return 1.0 + 0.3 * (po["won"] + 0.5 * po["replied"]) / max(1, tot)
    return 1.0


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def retrieve_one(ix: PersonaIndex, cfg: PipelineConfig, query: str, k: int, industry: str | None = None) -> list[Evidence]:
    cand = _search(ix, cfg, query, cfg.candidates)
    if cfg.graph:
        cand = rrf([cand, _graph_candidates(ix, query, industry)])[: cfg.candidates]
    idx = [i for i, _ in cand]
    if cfg.rerank and idx:
        rs = rerank(query, [ix.chunks[i].display for i in idx])
        scored = [(i, _sigmoid(s)) for i, s in zip(idx, rs)]
    else:  # calibrated-ish support score = dense cosine for every candidate
        import numpy as np
        from rag.index.models import embed
        q = embed([query])[0]
        scored = [(i, float(ix.dense.m[i] @ q)) for i in idx]
    if cfg.outcome_boost:
        scored = [(i, s * _outcome_factor(ix, ix.chunks[i])) for i, s in scored]
    if not cfg.rerank and cfg.retrieval == "hybrid":  # keep fused order but carry support score
        order = {i: r for r, (i, _) in enumerate(cand)}
        scored.sort(key=lambda x: (order[x[0]] - 8 * x[1]))
    else:
        scored.sort(key=lambda x: -x[1])
    out = []
    for i, s in scored[: k * 3]:
        c = ix.chunks[i]
        out.append(Evidence(c.doc_id, c.chunk_id, c.meta.get("type", ""), c.meta.get("title", ""), c.display, round(s, 4),
                            c.meta.get("project"), c.meta.get("outcome"), query, c.meta.get("date")))
    return out


def _dedupe_docs(evs: list[Evidence], k: int) -> list[Evidence]:
    seen, out = set(), []
    for e in evs:
        if e.doc_id not in seen:
            seen.add(e.doc_id)
            out.append(e)
        if len(out) >= k:
            break
    return out


def _corrective(ix: PersonaIndex, cfg: PipelineConfig, req: str, k: int, industry: str | None) -> tuple[list[Evidence], bool]:
    from rag.variants.v8_corrective import corrective_retrieve
    return corrective_retrieve(ix, cfg, req, k, industry)


def run(cfg: PipelineConfig, job: dict | str, persona: str, k: int = 8, requirements: list[str] | None = None,
        industry: str | None = None) -> RetrievalResult:
    job = job_query(job)
    ix = get_index(persona, cfg.chunking)
    whole = f"{job.get('title', '')}\n{job.get('description', '')}"
    min_support = config()["rag"]["min_support"]
    res = RetrievalResult([], variant=cfg.name)
    if cfg.query in ("decompose", "decompose_hyde"):
        reqs = requirements or extract_requirements(job)
        lists = []
        for r in reqs:
            if cfg.corrective:
                evs, weak = _corrective(ix, cfg, r, k, industry)
            else:
                evs = retrieve_one(ix, cfg, r, k, industry)
                weak = not evs or evs[0].score < min_support
            res.per_requirement[r] = _dedupe_docs(evs, 3)
            if weak:
                res.weak_requirements.append(r)
            lists.append([(id(e), e.score) for e in evs])
            res.queries.append(r)
        if cfg.query == "decompose_hyde":
            h = hyde_text(job, persona)
            evs = retrieve_one(ix, cfg, h, k, industry)
            res.queries.append(h)
            res.per_requirement["__hyde__"] = evs
        # merge per-requirement lists with RRF at document level
        doc_scores: dict[str, float] = {}
        best: dict[str, Evidence] = {}
        for evs in res.per_requirement.values():
            for rank, e in enumerate(_dedupe_docs(evs, k)):
                doc_scores[e.doc_id] = doc_scores.get(e.doc_id, 0) + 1 / (60 + rank + 1)
                if e.doc_id not in best or e.score > best[e.doc_id].score:
                    best[e.doc_id] = e
        res.evidence = [best[d] for d, _ in sorted(doc_scores.items(), key=lambda x: -x[1])][:k]
        res.per_requirement.pop("__hyde__", None)
    else:
        q = hyde_text(job, persona) if cfg.query == "hyde" else whole
        res.queries.append(q)
        if cfg.corrective:
            evs, weak = _corrective(ix, cfg, q, k, industry)
        else:
            evs = retrieve_one(ix, cfg, q, k, industry)
        res.evidence = _dedupe_docs(evs, k)
    if cfg.chunking == "multivector":  # group: return one item per project, best chunk wins
        seen, grouped = set(), []
        for e in res.evidence:
            key = e.project or e.doc_id
            if key not in seen:
                seen.add(key)
                grouped.append(e)
        # expand each project to its sibling docs (case + repo) for the writer
        out = []
        for e in grouped:
            out.append(e)
            for i in ix.project_docs.get(e.project or "", []):
                c = ix.chunks[i]
                if c.doc_id != e.doc_id and c.doc_id not in {x.doc_id for x in out} and c.meta.get("type") in ("case_study", "repo_readme"):
                    out.append(Evidence(c.doc_id, c.chunk_id, c.meta.get("type", ""), c.meta.get("title", ""), c.display, e.score * 0.99, e.project))
                    break
        res.evidence = out[:k]
    return res
