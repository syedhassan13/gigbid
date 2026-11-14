"""V7 query: HyDE - retrieve with a hypothetical ideal proposal written for the job."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v7_hyde", chunking="structure", query="hyde", retrieval="dense")
