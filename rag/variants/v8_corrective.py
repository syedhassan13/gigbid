"""V8 agentic (Corrective RAG, Yan et al. 2024) as a small LangGraph loop:

retrieve -> grade -> (good: done) | (weak, tries left: rewrite query -> retrieve) | (still weak: refuse to claim)

Grading uses the cross-encoder support score; rewriting uses the LLM when
available, otherwise a deterministic expansion from the persona's skill graph.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agent import llm
from agent.settings import config
from rag.index.models import tokenize
from rag.pipeline import PipelineConfig, retrieve_one

CONFIG = PipelineConfig(name="v8_corrective", chunking="structure", query="decompose", retrieval="hybrid", rerank=True, corrective=True)


class CState(TypedDict, total=False):
    query: str
    original: str
    evidence: list
    tries: int
    weak: bool


def corrective_retrieve(ix, cfg: PipelineConfig, query: str, k: int, industry: str | None):
    min_support = config()["rag"]["min_support"]

    def retrieve(s: CState) -> CState:
        return {"evidence": retrieve_one(ix, cfg, s["query"], k, industry)}

    def grade(s: CState) -> CState:
        ev = s["evidence"]
        return {"weak": not ev or ev[0].score < min_support}

    def rewrite(s: CState) -> CState:
        out = llm.complete_text("router", "Rewrite this freelance job requirement as a short search query listing concrete skills, "
                                "libraries and synonyms. Output only the query.", llm.untrusted("REQUIREMENT", s["original"]), max_tokens=60)
        if not out:  # deterministic expansion: add skills that co-occur with the requirement's tokens in the skill graph
            toks = set(tokenize(s["original"]))
            related = [sk for sk, projs in ix.skill_projects.items() if set(tokenize(sk)) & toks]
            out = s["original"] + " " + " ".join(related[:6])
        return {"query": out, "tries": s.get("tries", 0) + 1}

    def route(s: CState) -> str:
        if not s["weak"]:
            return "done"
        return "rewrite" if s.get("tries", 0) < 1 else "refuse"

    def refuse(s: CState) -> CState:
        return {"evidence": [], "weak": True}

    g = StateGraph(CState)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("rewrite", rewrite)
    g.add_node("refuse", refuse)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, {"done": END, "rewrite": "rewrite", "refuse": "refuse"})
    g.add_edge("rewrite", "retrieve")
    g.add_edge("refuse", END)
    out = g.compile().invoke({"query": query, "original": query, "tries": 0})
    return out["evidence"], out["weak"]
