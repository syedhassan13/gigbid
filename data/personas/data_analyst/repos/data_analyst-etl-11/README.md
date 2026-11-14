---
id: "repo:data_analyst-etl-11"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-etl-11"
skills: ["SQL", "data engineering", "ETL", "BigQuery", "dbt", "airflow", "fivetran"]
date: "2023-05-15"
client_industry: "e-commerce"
synthetic: true
---
# etl-service

Internal codename for the e-commerce engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import dbt
import airflow
import fivetran

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses dbt
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- dbt
- airflow
- fivetran
