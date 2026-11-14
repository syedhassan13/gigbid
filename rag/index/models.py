"""Open embedding + reranker models (CPU, ONNX via fastembed), BM25, and a flat
exact-search vector store persisted to disk.

Why a flat store: each persona corpus is ~200 documents / <1,000 chunks, so
exact cosine search is ~1 ms and avoids ANN recall loss (docs/adr/0003).
"""
from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from agent.settings import HOME, config

CACHE = HOME / "var" / "emb_cache"


@lru_cache
def _embedder():
    from fastembed import TextEmbedding
    c = config()["embeddings"]
    return TextEmbedding(c["model"], cache_dir=str(HOME / c["cache_dir"]))


@lru_cache
def _reranker(name: str | None = None):
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(name or config()["reranker"]["model"], cache_dir=str(HOME / config()["embeddings"]["cache_dir"]))


def embed(texts: list[str]) -> np.ndarray:
    """Embeddings with an on-disk cache keyed by text hash (incremental re-index is cheap)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    model = config()["embeddings"]["model"].replace("/", "_")
    keys = [hashlib.sha1((model + t).encode()).hexdigest() for t in texts]
    out: list[np.ndarray | None] = []
    missing = []
    for i, k in enumerate(keys):
        p = CACHE / f"{k}.npy"
        if p.exists():
            out.append(np.load(p))
        else:
            out.append(None)
            missing.append(i)
    if missing:
        vecs = list(_embedder().embed([texts[i] for i in missing], batch_size=32))
        for i, v in zip(missing, vecs):
            v = np.asarray(v, dtype=np.float32)
            np.save(CACHE / f"{keys[i]}.npy", v)
            out[i] = v
    m = np.vstack(out) if out else np.zeros((0, 384), dtype=np.float32)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def rerank(query: str, docs: list[str]) -> list[float]:
    if not docs:
        return []
    return [float(s) for s in _reranker().rerank(query, docs, batch_size=32)]


_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")
_STOP = set("the a an and or to of for in on with we our is are be you your this that it as at by from i my me will was".split())


def tokenize(text: str) -> list[str]:
    """Code-aware tokenizer: keeps 'next.js', 'c++', splits snake/camel for identifiers."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    toks = []
    for t in _TOKEN.findall(text.lower().replace("_", " ")):
        t = t.strip(".-")
        if t and t not in _STOP:
            toks.append(t)
    return toks


class DenseIndex:
    def __init__(self, texts: list[str]):
        self.m = embed(texts)

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        if len(self.m) == 0:
            return []
        q = embed([query])[0]
        s = self.m @ q
        idx = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in idx]


class SparseIndex:
    def __init__(self, texts: list[str]):
        self.bm = BM25Okapi([tokenize(t) or ["_"] for t in texts])

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        s = self.bm.get_scores(tokenize(query) or ["_"])
        idx = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in idx if s[i] > 0]


def rrf(rankings: list[list[tuple[int, float]]], k: int = 60) -> list[tuple[int, float]]:
    agg: dict[int, float] = {}
    for r in rankings:
        for rank, (i, _) in enumerate(r):
            agg[i] = agg.get(i, 0.0) + 1.0 / (k + rank + 1)
    return sorted(agg.items(), key=lambda x: -x[1])


def offline() -> bool:
    return os.getenv("GIGBID_NO_MODELS") == "1"
