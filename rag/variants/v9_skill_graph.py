"""V9 agentic: skill graph (GraphRAG-lite) - skills/libraries -> projects -> clients/industries -> outcomes,
fused with hybrid retrieval. Answers "have I done X for a client in Y industry?"."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v9_skill_graph", chunking="structure", query="decompose", retrieval="hybrid", graph=True)
