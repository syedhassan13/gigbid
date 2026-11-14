"""Shipped pipeline, chosen by measurement (evals/results/rag_variants.json + rag_combinations.json):
contextual chunks (V6) + hybrid BM25/dense RRF (V2) + outcome-aware boost (V4), whole-job query.
The earlier candidate (decomposition + cross-encoder rerank) lost: the MS-MARCO reranker and
per-requirement decomposition both lowered document-level Recall@5 on this corpus."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v_best", chunking="contextual", query="whole", retrieval="hybrid", rerank=False, outcome_boost=True)
