"""Chunking strategies. Each chunk keeps its parent doc id + metadata.

fixed       V0: fixed-size character windows, no structure.
structure   markdown sections; code fences become their own chunks.
contextual  V6: structure chunks with a generated context line prepended.
multivector V5: summary / README prose / code chunks indexed separately,
            all mapped back to the same `project` so results group by project.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from rag.ingest.loaders import Document


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str             # text that is embedded / indexed
    display: str          # text shown to writer / UI (without context line)
    meta: dict = field(default_factory=dict)


def _cid(doc_id: str, i: int, text: str) -> str:
    return f"{doc_id}#{i}-{hashlib.md5(text.encode()).hexdigest()[:6]}"


def _meta(d: Document) -> dict:
    m = dict(d.meta)
    m.update({"doc_id": d.doc_id, "type": d.type, "persona": d.persona, "title": d.title})
    return m


def fixed(docs: list[Document], size: int = 500, overlap: int = 50) -> list[Chunk]:
    out = []
    for d in docs:
        t = d.text
        for i, start in enumerate(range(0, max(1, len(t)), size - overlap)):
            piece = t[start:start + size]
            if piece.strip():
                out.append(Chunk(_cid(d.doc_id, i, piece), d.doc_id, piece, piece, _meta(d)))
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (kind, text) where kind is prose|code."""
    parts, pos = [], 0
    for m in re.finditer(r"```.*?```", text, flags=re.S):
        if m.start() > pos:
            parts.append(("prose", text[pos:m.start()]))
        parts.append(("code", m.group(0)))
        pos = m.end()
    parts.append(("prose", text[pos:]))
    out = []
    for kind, t in parts:
        if kind == "code":
            out.append(("code", t))
            continue
        for sec in re.split(r"\n(?=#{1,3} )", t):
            if sec.strip():
                out.append(("prose", sec.strip()))
    return out


def structure(docs: list[Document], max_chars: int = 900) -> list[Chunk]:
    out = []
    for d in docs:
        if d.type in ("proposal", "review"):
            out.append(Chunk(_cid(d.doc_id, 0, d.text), d.doc_id, d.text, d.text, {**_meta(d), "kind": "prose"}))
            continue
        for i, (kind, sec) in enumerate(_sections(d.text)):
            for j in range(0, len(sec), max_chars):
                piece = sec[j:j + max_chars]
                if len(piece.strip()) > 20:
                    out.append(Chunk(_cid(d.doc_id, i * 100 + j, piece), d.doc_id, piece, piece, {**_meta(d), "kind": kind}))
    return out


def context_line(c: Chunk) -> str:
    m = c.meta
    kind = {"case_study": "case study", "repo_readme": "repository README", "proposal": "past proposal", "review": "client review", "cv": "CV"}.get(m.get("type"), "document")
    bits = [f"From {m.get('persona')}'s {kind} '{m.get('title', '')}'"]
    if m.get("client_industry"):
        bits.append(f"client industry: {m['client_industry']}")
    if m.get("skills"):
        bits.append("skills: " + ", ".join(m["skills"][:8]))
    if m.get("kind") == "code":
        bits.append("this chunk is source code from that project")
    if m.get("outcome"):
        bits.append(f"outcome: {m['outcome']}")
    return "[" + "; ".join(bits) + "]"


def contextual(docs: list[Document]) -> list[Chunk]:
    """Anthropic-style contextual retrieval; the context line is generated from
    document metadata (deterministic, zero-cost) - an LLM-written variant can be
    enabled with GIGBID_CONTEXT_LLM=1 at index time."""
    out = []
    for c in structure(docs):
        c.text = context_line(c) + "\n" + c.text
        out.append(c)
    return out


def multivector(docs: list[Document]) -> list[Chunk]:
    out = []
    for c in structure(docs):
        c.meta["vector_kind"] = "code" if c.meta.get("kind") == "code" else ("readme" if c.meta.get("type") == "repo_readme" else "prose")
        out.append(c)
    # one synthetic "summary" vector per project from its metadata
    by_project: dict[str, Document] = {}
    for d in docs:
        if d.meta.get("project") and d.type in ("case_study", "repo_readme"):
            by_project.setdefault(d.meta["project"], d)
    for proj, d in by_project.items():
        skills = sorted({s for x in docs if x.meta.get("project") == proj for s in x.meta.get("skills", [])})
        summ = f"Project summary: {d.title}. Skills and libraries: {', '.join(skills)}. Industry: {d.meta.get('client_industry')}."
        out.append(Chunk(_cid(d.doc_id, 9999, summ), d.doc_id, summ, summ, {**_meta(d), "vector_kind": "summary"}))
    return out


CHUNKERS = {"fixed": fixed, "structure": structure, "contextual": contextual, "multivector": multivector}
