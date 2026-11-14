---
id: "repo:ai_ml-forecast-12"
type: "repo_readme"
persona: "ai_ml"
project: "ai_ml-forecast-12"
skills: ["Python", "time series", "forecasting", "machine learning", "prophet", "lightgbm", "statsmodels"]
date: "2022-05-15"
client_industry: "real estate"
synthetic: true
---
# forecast-service

Internal codename for the real estate engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import prophet
import lightgbm
import statsmodels

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses prophet
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- prophet
- lightgbm
- statsmodels
