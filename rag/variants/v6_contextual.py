"""V6 indexing: contextual retrieval - a context line (persona, doc type, project, skills,
industry, outcome) is prepended to every chunk before indexing."""
from rag.pipeline import PipelineConfig

CONFIG = PipelineConfig(name="v6_contextual", chunking="contextual", query="whole", retrieval="hybrid")
