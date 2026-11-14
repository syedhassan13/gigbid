"""V0 baseline (required): fixed 500-char chunks, top-k cosine on the whole job post."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v0_naive", chunking="fixed", query="whole", retrieval="dense")
