---
id: "repo:fullstack-cms-migration-18"
type: "repo_readme"
persona: "fullstack"
project: "fullstack-cms-migration-18"
skills: ["WordPress", "Next.js", "SEO", "content migration", "contentful", "wp-graphql", "redirects"]
date: "2024-05-15"
client_industry: "education"
synthetic: true
---
# cms-migration-service

Internal codename for the education engagement. Setup: copy `.env.example`, install dependencies, run the entrypoint.

## Architecture
- ingestion -> processing -> storage -> API
- jobs run asynchronously; failures retry with backoff
- config is environment-driven

## Core module

```ts
import Contentful from 'contentful';
import WpGraphql from 'wp-graphql';
import Redirects from 'redirects';

export async function handler(req, res) {
  // core flow built on contentful
  const result = await service.run(req.body);
  res.json(result);
}
```

## Dependencies
- contentful
- wp-graphql
- redirects
