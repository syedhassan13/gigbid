---
id: "repo:data_analyst-kpi-looker-09"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-kpi-looker-09"
skills: ["Looker", "SQL", "KPI reporting", "data modeling", "lookml", "dbt", "postgres"]
date: "2026-05-15"
client_industry: "media"
synthetic: true
---
# kpi-looker-service

Internal codename for the media engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import lookml
import dbt
import postgres

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses lookml
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- lookml
- dbt
- postgres
