---
id: "repo:data_analyst-survey-05"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-survey-05"
skills: ["survey analysis", "Python", "data visualization", "Tableau", "pandas", "textblob", "likert"]
date: "2026-05-15"
client_industry: "hospitality"
synthetic: true
---
# survey-service

Internal codename for the hospitality engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import pandas
import textblob
import likert

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses pandas
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- pandas
- textblob
- likert
