---
id: "repo:data_analyst-ab-test-13"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-ab-test-13"
skills: ["A/B testing", "statistics", "Python", "SQL", "scipy", "statsmodels", "bayesian"]
date: "2024-05-15"
client_industry: "media"
synthetic: true
---
# ab-test-service

Internal codename for the media engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import scipy
import statsmodels
import bayesian

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses scipy
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- scipy
- statsmodels
- bayesian
