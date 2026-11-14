"""V3 retrieval (required): hybrid candidates re-scored by an open cross-encoder."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v3_rerank", chunking="structure", query="whole", retrieval="hybrid", rerank=True)
