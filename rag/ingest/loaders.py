"""Loaders: Markdown (front matter), JSONL (reviews, proposals), PDF CVs, and
GitHub repos (through the GitHub MCP server, see rag/ingest/github_mcp.py).
Every Document carries metadata: persona, type, project, skills, date,
client_industry and, for proposals, outcome.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERSONAS = ROOT / "data" / "personas"


@dataclass
class Document:
    doc_id: str
    type: str                 # cv | case_study | repo_readme | proposal | review | user_upload
    persona: str
    text: str
    title: str = ""
    meta: dict = field(default_factory=dict)


def _front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                meta[k.strip()] = json.loads(v.strip())
            except json.JSONDecodeError:
                meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def load_markdown(path: Path, persona: str) -> Document:
    meta, body = _front_matter(path.read_text(encoding="utf-8"))
    title = next((l[2:].strip() for l in body.splitlines() if l.startswith("# ")), path.stem)
    return Document(meta.get("id", f"file:{path.stem}"), meta.get("type", "user_upload"), persona, body, title, meta)


def load_pdf(path: Path, persona: str, doc_type: str = "cv") -> Document:
    from pypdf import PdfReader
    text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return Document(f"{doc_type}:{persona}:{path.stem}", doc_type, persona, text, path.stem, {"type": doc_type, "source": path.name})


def load_jsonl(path: Path, persona: str) -> list[Document]:
    docs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["type"] == "proposal":
            text = f"Proposal for job: {r['job_title']}\n\n{r['text']}"
            title = r["job_title"]
        else:
            text = f"Client review ({r.get('stars')}/5): {r['text']}"
            title = f"Review {r.get('project')}"
        docs.append(Document(r["id"], r["type"], persona, text, title, r))
    return docs


def load_persona(persona: str, extra_dir: Path | None = None) -> list[Document]:
    d = PERSONAS / persona
    docs: list[Document] = []
    if (d / "cv.md").exists():
        docs.append(load_markdown(d / "cv.md", persona))
    for p in sorted(d.glob("cv*.pdf")):
        docs.append(load_pdf(p, persona))
    for p in sorted((d / "case_studies").glob("*.md")):
        docs.append(load_markdown(p, persona))
    for p in sorted((d / "repos").glob("*/README.md")):
        docs.append(load_markdown(p, persona))
    for name in ("reviews.jsonl", "proposals.jsonl"):
        if (d / name).exists():
            docs += load_jsonl(d / name, persona)
    up = extra_dir or (ROOT / "var" / "uploads" / persona)
    if up.exists():  # user-added work (incremental re-index picks these up)
        for p in sorted(up.glob("*.md")):
            docs.append(load_markdown(p, persona))
        for p in sorted(up.glob("*.pdf")):
            docs.append(load_pdf(p, persona, "user_upload"))
    return docs
