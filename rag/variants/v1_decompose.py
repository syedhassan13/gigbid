"""V1 query (required): one retrieval per extracted requirement, merged with RRF."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v1_decompose", chunking="structure", query="decompose", retrieval="dense")
