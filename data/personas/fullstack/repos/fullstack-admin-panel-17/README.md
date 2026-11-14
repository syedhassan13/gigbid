---
id: "repo:fullstack-admin-panel-17"
type: "repo_readme"
persona: "fullstack"
project: "fullstack-admin-panel-17"
skills: ["React", "Django", "role-based access", "Python", "react-admin", "django-guardian", "pytest"]
date: "2026-05-15"
client_industry: "e-commerce"
synthetic: true
---
# admin-panel-service

Internal codename for the e-commerce engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```ts
import ReactAdmin from 'react-admin';
import DjangoGuardian from 'django-guardian';
import Pytest from 'pytest';

export async function handler(req, res) {
  // core flow built on react-admin
  const result = await service.run(req.body);
  res.json(result);
}
```

## Dependencies
- react-admin
- django-guardian
- pytest
