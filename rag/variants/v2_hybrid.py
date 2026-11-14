"""V2 retrieval (required): BM25 (code-aware tokens) + dense, reciprocal rank fusion.
Catches exact library names ("celery", "dbt") that embeddings blur."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v2_hybrid", chunking="structure", query="whole", retrieval="hybrid")
