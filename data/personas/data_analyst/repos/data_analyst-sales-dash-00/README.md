---
id: "repo:data_analyst-sales-dash-00"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-sales-dash-00"
skills: ["Power BI", "SQL", "DAX", "data visualization", "power query", "sql server", "row-level security"]
date: "2022-05-15"
client_industry: "education"
synthetic: true
---
# sales-dash-service

Internal codename for the education engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import power_query
import sql_server
import row_level_security

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses power query
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- power query
- sql server
- row-level security
