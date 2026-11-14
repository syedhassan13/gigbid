---
id: "repo:fullstack-saas-dash-00"
type: "repo_readme"
persona: "fullstack"
project: "fullstack-saas-dash-00"
skills: ["React", "TypeScript", "Node.js", "PostgreSQL", "recharts", "prisma", "tanstack-query"]
date: "2023-05-15"
client_industry: "healthcare"
synthetic: true
---
# saas-dash-service

Internal codename for the healthcare engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```ts
import Recharts from 'recharts';
import Prisma from 'prisma';
import TanstackQuery from 'tanstack-query';

export async function handler(req, res) {
  // core flow built on recharts
  const result = await service.run(req.body);
  res.json(result);
}
```

## Dependencies
- recharts
- prisma
- tanstack-query
