---
id: "repo:ai_ml-speech-17"
type: "repo_readme"
persona: "ai_ml"
project: "ai_ml-speech-17"
skills: ["speech recognition", "LLM", "Python", "AWS", "whisper", "ffmpeg", "boto3"]
date: "2023-05-15"
client_industry: "manufacturing"
synthetic: true
---
# speech-service

Internal codename for the manufacturing engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```python
import whisper
import ffmpeg
import boto3

def run_pipeline(config):
    """Entry point used by the scheduler."""
    data = load_inputs(config["source"])
    model = build_model(config)  # uses whisper
    results = model.process(data)
    persist(results, config["target"])
    return results
```

## Dependencies
- whisper
- ffmpeg
- boto3
