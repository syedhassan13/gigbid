---
id: "repo:ai_ml-ner-18"
type: "repo_readme"
persona: "ai_ml"
project: "ai_ml-ner-18"
skills: ["NLP", "named entity recognition", "Python", "LLM", "spacy", "pydantic", "pdfplumber"]
date: "2021-05-15"
client_industry: "hospitality"
synthetic: true
---
# ner-service

Internal codename for the hospitality engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import spacy
import pydantic
import pdfplumber

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses spacy
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- spacy
- pydantic
- pdfplumber
