"""V5 indexing: summary / README / code chunks indexed separately, returned grouped per project."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v5_multivector", chunking="multivector", query="whole", retrieval="hybrid")
