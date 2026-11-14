---
id: "repo:data_analyst-survey-15"
type: "repo_readme"
persona: "data_analyst"
project: "data_analyst-survey-15"
skills: ["survey analysis", "Python", "data visualization", "Tableau", "pandas", "textblob", "likert"]
date: "2023-05-15"
client_industry: "manufacturing"
synthetic: true
---
# survey-service

Internal codename for the manufacturing engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

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
