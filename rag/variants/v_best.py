"""Shipped pipeline (chosen by evals/results/rag_variants.json; see docs/DATA_CARD.md decision paragraph)."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v_best", chunking="contextual", query="decompose", retrieval="hybrid", rerank=True, outcome_boost=True)
