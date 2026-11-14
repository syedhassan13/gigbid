---
id: "repo:ai_ml-churn-deploy-16"
type: "repo_readme"
persona: "ai_ml"
project: "ai_ml-churn-deploy-16"
skills: ["machine learning", "Python", "MLOps", "Docker", "mlflow", "xgboost", "celery"]
date: "2021-05-15"
client_industry: "hospitality"
synthetic: true
---
# churn-deploy-service

Internal codename for the hospitality engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import mlflow
import xgboost
import celery

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses mlflow
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- mlflow
- xgboost
- celery
