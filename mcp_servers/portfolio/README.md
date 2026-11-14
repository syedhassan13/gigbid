# gigbid-portfolio-mcp

A read-only MCP server that turns a freelancer portfolio (CV, case studies, repo READMEs, client reviews,
and past proposals with outcomes) into **citable evidence** for an AI host such as Claude Desktop or Cursor.

* **Tools:** `search_evidence(requirement, k, filters)` returns evidence items with type, source URI, date,
  outcome and a support score, plus a `weak` flag that tells the host when it must **not** claim a skill.
  `get_case_study(id)` loads one item. `list_skills()` lists provable skills with evidence counts.
* **Resources:** `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{id}`, `portfolio://cv/{persona}`.
* **Prompts:** "Answer a screening question from my portfolio", "Prove fit for a job post", "Which of my past proposals worked?".
* **Retrieval:** contextual chunks + hybrid BM25/dense (bge-small, CPU) + outcome-aware boost. This is the
  variant that won GigBid's evaluation.

## Install & run

```bash
# with uv (no clone needed)
uvx --from "git+https://github.com/syedhassan13/gigbid" gigbid-portfolio-mcp --persona ai_ml

# your own portfolio: a folder <dir>/<name>/ with cv.md, case_studies/*.md, repos/*/README.md, proposals.jsonl, reviews.jsonl
GIGBID_PORTFOLIO_DIR=/path/to/portfolios GIGBID_HOME=~/.gigbid uvx --from "git+https://github.com/syedhassan13/gigbid" gigbid-portfolio-mcp --persona <name>

# Streamable HTTP instead of stdio
gigbid-portfolio-mcp --http --port 8201

# Docker
docker build -f infra/docker/python.Dockerfile -t gigbid . && docker run -p 8201:8201 -e MCP_HOST=0.0.0.0 gigbid python -m mcp_servers.portfolio.server --http
```

### Claude Desktop (`claude_desktop_config.json`)
```json
{ "mcpServers": { "portfolio": { "command": "uvx",
  "args": ["--from", "git+https://github.com/syedhassan13/gigbid", "gigbid-portfolio-mcp", "--persona", "ai_ml"] } } }
```

The bundled demo portfolios (`ai_ml`, `fullstack`, `data_analyst`) are **synthetic**.
