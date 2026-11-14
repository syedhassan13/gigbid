---
id: "repo:ai_ml-rag-chatbot-00"
type: "repo_readme"
persona: "ai_ml"
project: "ai_ml-rag-chatbot-00"
skills: ["Python", "LLM", "RAG", "FastAPI", "embeddings", "faiss", "langchain", "sentence-transformers"]
date: "2024-05-15"
client_industry: "education"
synthetic: true
---
# rag-chatbot-service

Internal codename for the education engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import faiss
import langchain
import sentence_transformers

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses faiss
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- faiss
- langchain
- sentence-transformers
