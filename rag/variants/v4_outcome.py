"""V4 ranking: outcome-aware boost - evidence from proposals that won / got replies
(and projects whose proposals won) ranks higher; ignored proposals are demoted."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v4_outcome", chunking="structure", query="whole", retrieval="hybrid", rerank=True, outcome_boost=True)
