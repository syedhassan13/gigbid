"""Retriever factory: the deployed variant is chosen by config (rag.variant), which is
set from the evaluation results - never by default."""
from __future__ import annotations

import importlib

from agent.settings import config
from rag.pipeline import PipelineConfig, RetrievalResult, run

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_multivector",
            "v6_contextual", "v7_hyde", "v8_corrective", "v9_skill_graph", "v_best"]


def variant_config(name: str | None = None) -> PipelineConfig:
    name = name or config()["rag"]["variant"]
    return importlib.import_module(f"rag.variants.{name}").CONFIG


def retrieve(job: dict | str, persona: str, k: int | None = None, variant: str | None = None,
             requirements: list[str] | None = None, industry: str | None = None) -> RetrievalResult:
    return run(variant_config(variant), job, persona, k or config()["rag"]["k"], requirements, industry)
