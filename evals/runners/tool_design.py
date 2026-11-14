"""R&D question A: does tool granularity change agent behaviour?

40 tasks with known correct calls; three tool sets exposed to the same open model:
  fine     - the real per-operation MCP tools (search_jobs, get_job, get_client_history, ...)
  coarse   - 2 tools: marketplace(action, params) and portfolio(action, params)
  best     - the fine set with rewritten, disambiguating descriptions
Metrics: tool-selection accuracy, argument accuracy, tokens per task.

    python -m evals.runners.tool_design         (needs an LLM profile, e.g. GROQ_API_KEY)
"""
from __future__ import annotations

import json
import time

from agent import llm
from agent.settings import profile
from evals.runners.common import mean, write

J, C, T = "j-7f3a1c9e20", "c-91ab33d0", "t-4c2e9a"
TASKS = [  # (instruction, tool, required args)
    ("Find new LLM jobs for my saved search.", "search_jobs", {"query": "LLM"}),
    ("Search for Power BI dashboard jobs posted after 2026-11-10T00:00.", "search_jobs", {"query": "Power BI dashboard", "posted_after": "2026-11-10T00:00"}),
    ("Show me up to 5 React jobs.", "search_jobs", {"query": "React", "limit": 5}),
    ("Look for data analytics category jobs mentioning dbt.", "search_jobs", {"query": "dbt", "category": "data_analytics"}),
    ("Any new Stripe integration work?", "search_jobs", {"query": "Stripe"}),
    ("Search jobs about computer vision defect detection.", "search_jobs", {"query": "computer vision defect detection"}),
    (f"Open job {J} and read its description.", "get_job", {"job_id": J}),
    (f"What screening questions does job {J} have?", "get_job", {"job_id": J}),
    (f"How many Connects does job {J} cost?", "get_job", {"job_id": J}),
    (f"What's the budget on {J}?", "get_job", {"job_id": J}),
    (f"Has client {C} verified their payment method?", "get_client_history", {"client_id": C}),
    (f"How much has client {C} spent and how many hires?", "get_client_history", {"client_id": C}),
    (f"What do freelancers say about client {C}?", "get_client_history", {"client_id": C}),
    (f"Is client {C} a risky new account?", "get_client_history", {"client_id": C}),
    ("How many Connects do I have left?", "get_connects_balance", {}),
    ("Can I afford to bid on three more jobs this week? Check my Connects.", "get_connects_balance", {}),
    ("What is the median budget for ai_ml jobs?", "get_market_stats", {"category": "ai_ml"}),
    ("Typical hourly rates in web_dev?", "get_market_stats", {"category": "web_dev"}),
    ("Pricing context for data_analytics fixed-price jobs.", "get_market_stats", {"category": "data_analytics"}),
    ("What is the current platform policy on Connects pricing?", "get_policy", {}),
    ("Are there any required statements I must include in proposals now?", "get_policy", {}),
    ("What happened to the proposals I submitted?", "list_proposals", {}),
    ("Show my pipeline of submitted proposals.", "list_proposals", {}),
    ("Do I have any client conversations?", "list_threads", {}),
    ("Which clients replied to me?", "list_threads", {}),
    (f"Read the messages in thread {T}.", "list_messages", {"thread_id": T}),
    (f"What did the client say last in {T}?", "list_messages", {"thread_id": T}),
    ("Any new marketplace events since sequence 40?", "get_events", {"after": 40}),
    ("Did anything change since event 0?", "get_events", {"after": 0}),
    ("Find portfolio proof that I have used Celery for background jobs.", "search_evidence", {"requirement": "Celery"}),
    ("Do I have evidence of Power BI row-level security work?", "search_evidence", {"requirement": "Power BI row-level security"}),
    ("Find my best case study proving RAG chatbot experience.", "search_evidence", {"requirement": "RAG chatbot"}),
    ("Have I done Stripe subscription billing before?", "search_evidence", {"requirement": "Stripe subscription billing"}),
    ("Proof for 'time series forecasting with LightGBM'.", "search_evidence", {"requirement": "time series forecasting LightGBM"}),
    ("Load the full case study case:ai_ml-forecast-02.", "get_case_study", {"id": "case:ai_ml-forecast-02"}),
    ("Open repo:fullstack-booking-02 in full.", "get_case_study", {"id": "repo:fullstack-booking-02"}),
    ("Show the complete text of proposal:data_analyst-010.", "get_case_study", {"id": "proposal:data_analyst-010"}),
    ("What skills can my portfolio prove?", "list_skills", {}),
    ("List the technologies I have evidence for.", "list_skills", {}),
    ("Which libraries appear most in my portfolio?", "list_skills", {}),
]

FINE = {
    "search_jobs": ("Search open jobs.", {"query": "string", "category": "string", "posted_after": "string", "limit": "integer"}),
    "get_job": ("Get a job.", {"job_id": "string"}),
    "get_client_history": ("Get client.", {"client_id": "string"}),
    "get_connects_balance": ("Connects balance.", {}),
    "get_market_stats": ("Market stats.", {"category": "string"}),
    "get_policy": ("Policy.", {}),
    "list_proposals": ("List proposals.", {}),
    "list_threads": ("List threads.", {}),
    "list_messages": ("List messages.", {"thread_id": "string"}),
    "get_events": ("Events.", {"after": "integer"}),
    "search_evidence": ("Search evidence.", {"requirement": "string"}),
    "get_case_study": ("Get item.", {"id": "string"}),
    "list_skills": ("Skills.", {}),
}
BEST_DESC = {
    "search_jobs": "Search OPEN job posts by keywords (saved-search style). Use for 'find/any new/show jobs'. Not for a specific job id.",
    "get_job": "Get ONE job post by its id (j-...): description, budget, screening questions, Connects cost.",
    "get_client_history": "Get a CLIENT's public history by client id (c-...): payment verified, total spent, hires, rating, reviews.",
    "get_connects_balance": "The signed-in freelancer's remaining Connects (bidding credits).",
    "get_market_stats": "Budget / hourly-rate percentiles for a job CATEGORY (ai_ml, web_dev, data_analytics, ...). Pricing context.",
    "get_policy": "Current platform policy: Connects price table, required proposal statements, limits.",
    "list_proposals": "The freelancer's SUBMITTED proposals and their status (pipeline).",
    "list_threads": "Client conversation threads (who replied) with their last message.",
    "list_messages": "All messages in ONE client thread by thread id (t-...).",
    "get_events": "Marketplace events after a sequence number (status changes, client replies).",
    "search_evidence": "Search the freelancer's OWN PORTFOLIO for proof of one skill/requirement. Use for 'have I done X / proof / evidence'.",
    "get_case_study": "Load ONE portfolio item in full by evidence id (case:..., repo:..., proposal:...).",
    "list_skills": "List the skills/libraries the freelancer's portfolio can prove, with counts.",
}


def tool_schema(name: str, desc: str, props: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in props.items()}}}}


def toolsets() -> dict[str, list[dict]]:
    fine = [tool_schema(n, d, p) for n, (d, p) in FINE.items()]
    best = [tool_schema(n, BEST_DESC[n], p) for n, (_, p) in FINE.items()]
    mk = [n for n in FINE if n not in ("search_evidence", "get_case_study", "list_skills")]
    coarse = [
        {"type": "function", "function": {"name": "marketplace", "description": f"Marketplace operations. action one of {mk}.",
                                          "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": mk}, "params": {"type": "object"}}, "required": ["action"]}}},
        {"type": "function", "function": {"name": "portfolio", "description": "Portfolio operations. action one of search_evidence, get_case_study, list_skills.",
                                          "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["search_evidence", "get_case_study", "list_skills"]}, "params": {"type": "object"}}, "required": ["action"]}}},
    ]
    return {"fine": fine, "coarse": coarse, "best": best}


def call_once(tools: list[dict], task: str) -> tuple[str | None, dict, int]:
    import httpx
    import os
    p = profile()
    body = {"model": p["nodes"].get("router", p["nodes"]["default"]), "temperature": 0, "tool_choice": "required", "tools": tools,
            "messages": [{"role": "system", "content": "You are a freelancer's assistant. Call exactly one tool to serve the request."},
                         {"role": "user", "content": task}]}
    for _ in range(4):
        r = httpx.post(f"{p['base_url']}/chat/completions", json=body, timeout=60, headers={"Authorization": f"Bearer {os.environ[p['api_key_env']]}"})
        if r.status_code == 429:
            time.sleep(float(r.headers.get("retry-after", 3)))
            continue
        d = r.json()
        tok = d.get("usage", {}).get("total_tokens", 0)
        calls = (d.get("choices") or [{}])[0].get("message", {}).get("tool_calls") or []
        if not calls:
            return None, {}, tok
        f = calls[0]["function"]
        args = json.loads(f.get("arguments") or "{}")
        if f["name"] in ("marketplace", "portfolio"):
            return args.get("action"), args.get("params") or {}, tok
        return f["name"], args, tok
    return None, {}, 0


def args_ok(got: dict, want: dict) -> bool:
    for k, v in want.items():
        g = got.get(k)
        if isinstance(v, str):
            if not isinstance(g, str) or not (v.lower() in g.lower() or g.lower() in v.lower()):
                return False
        elif g != v:
            return False
    return True


def main() -> None:
    if not llm.available():
        raise SystemExit("R&D A needs an LLM profile (set GROQ_API_KEY). No numbers are produced offline.")
    out = {}
    for name, tools in toolsets().items():
        sel, arg, toks, rows = [], [], [], []
        for task, tool, want in TASKS:
            got_tool, got_args, tok = call_once(tools, task)
            sel.append(got_tool == tool)
            arg.append(got_tool == tool and args_ok(got_args, want))
            toks.append(tok)
            rows.append({"task": task, "expected": tool, "got": got_tool, "args": got_args, "ok": got_tool == tool})
        out[name] = {"tool_selection_accuracy": mean(sel), "argument_accuracy": mean(arg), "tokens_per_task": mean(toks),
                     "n_tools": len(tools), "errors": [r for r in rows if not r["ok"]]}
        print(name, {k: v for k, v in out[name].items() if k != "errors"})
    write("tool_design", {"tasks": len(TASKS), "model": profile()["nodes"].get("router"), "results": out,
                          "hypothesis": "Fine-grained tools with disambiguating descriptions beat coarse action-dispatch tools on argument accuracy at a modest token cost."})


if __name__ == "__main__":
    main()
