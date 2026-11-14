"""Ingest a user's GitHub repos into the portfolio THROUGH the official GitHub MCP server
(never by scraping). Writes Markdown documents (README + key code files) to the user's upload
folder; the next retrieval call re-indexes incrementally (only new chunks are embedded).

    GITHUB_TOKEN=... python -m rag.ingest.github_mcp --owner <user> --persona ai_ml --max-repos 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from agent.settings import HOME

GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")


async def ingest(owner: str, persona: str, max_repos: int = 10) -> list[str]:
    from langchain_mcp_adapters.client import MultiServerMCPClient
    client = MultiServerMCPClient({"github": {"transport": "streamable_http", "url": GITHUB_MCP_URL,
                                              "headers": {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}}})
    tools = {t.name: t for t in await client.get_tools()}
    repos_raw = await tools["search_repositories"].ainvoke({"query": f"user:{owner} fork:false", "perPage": max_repos})
    repos = json.loads(repos_raw) if isinstance(repos_raw, str) else repos_raw
    items = repos.get("items", repos) if isinstance(repos, dict) else repos
    out_dir = HOME / "var" / "uploads" / persona
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for r in items[:max_repos]:
        name = r["name"]
        try:
            readme = await tools["get_file_contents"].ainvoke({"owner": owner, "repo": name, "path": "README.md"})
        except Exception:
            continue
        text = readme if isinstance(readme, str) else json.dumps(readme)
        meta = {"id": f"repo:github-{owner}-{name}", "type": "repo_readme", "persona": persona, "project": f"github-{name}",
                "skills": [r.get("language")] if r.get("language") else [], "date": (r.get("pushed_at") or "")[:10],
                "source": r.get("html_url"), "synthetic": False}
        fm = "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in meta.items()) + "\n---\n"
        p = out_dir / f"github-{name}.md"
        p.write_text(fm + f"# {name}\n\n{r.get('description') or ''}\n\n{text[:20000]}", encoding="utf-8")
        written.append(str(p))
    from rag.pipeline import invalidate
    invalidate(persona)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--persona", required=True)
    ap.add_argument("--max-repos", type=int, default=10)
    a = ap.parse_args()
    print("\n".join(asyncio.run(ingest(a.owner, a.persona, a.max_repos))))
