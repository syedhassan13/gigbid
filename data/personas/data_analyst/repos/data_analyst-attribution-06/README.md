---
id: "repo:data_analyst-attribution-06"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-attribution-06"
skills: ["marketing analytics", "SQL", "Google Analytics", "Looker", "ga4", "bigquery", "lookml"]
date: "2021-05-15"
client_industry: "media"
synthetic: true
---
# attribution-service

Internal codename for the media engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import ga4
import bigquery
import lookml

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses ga4
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- ga4
- bigquery
- lookml
