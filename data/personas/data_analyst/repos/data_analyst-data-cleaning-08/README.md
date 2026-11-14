---
id: "repo:data_analyst-data-cleaning-08"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-data-cleaning-08"
skills: ["data cleaning", "Python", "Excel", "CRM", "recordlinkage", "rapidfuzz", "hubspot api"]
date: "2026-05-15"
client_industry: "education"
synthetic: true
---
# data-cleaning-service

Internal codename for the education engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import recordlinkage
import rapidfuzz
import hubspot_api

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses recordlinkage
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- recordlinkage
- rapidfuzz
- hubspot api
