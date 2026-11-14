"""Node wrapper: step/token budgets (C4), per-node timeout (C7), execution trace (C2)."""
from __future__ import annotations

import asyncio
import json
import time

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from agent.settings import ROOT
from agent.settings import config as app_config
from agent.state import trace_event
from agent.tracing import current_usage

PERSONAS = ROOT / "data" / "personas"


class BudgetExceeded(Exception):
    pass


def profile_of(persona: str) -> dict:
    p = PERSONAS / persona / "profile.json"
    return json.loads(p.read_text()) if p.exists() else {"persona": persona, "rate_floor": 30, "target_rate": 45, "skills": []}


def node(name: str, timeout: float = 120):
    """Decorate an async node fn(state, config, store) -> dict."""
    def deco(fn):
        async def wrapper(state: dict, config: RunnableConfig, *, store: BaseStore):
            b = app_config()["budgets"]
            if state.get("status") == "needs_attention":
                return {}
            if (state.get("steps") or 0) >= b["max_steps"] or (state.get("tokens") or 0) >= b["max_tokens"]:
                return {"status": "needs_attention", "error": f"budget exceeded before {name} (steps={state.get('steps')}, tokens={state.get('tokens')})",
                        "trace": trace_event(name, "budget_exceeded")}
            u = current_usage.get()
            t_before = (u.tokens_in + u.tokens_out) if u else 0
            c_before = u.cost_usd if u else 0.0
            t0 = time.time()
            try:
                out = await asyncio.wait_for(fn(state, config or {}, store), timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"node {name} timed out after {timeout}s")
            out = dict(out or {})
            dt = time.time() - t0
            tok = ((u.tokens_in + u.tokens_out) - t_before) if u else 0
            cost = (u.cost_usd - c_before) if u else 0.0
            out["steps"] = 1
            out["tokens"] = tok
            out["cost_usd"] = cost
            out["trace"] = list(out.get("trace") or []) + trace_event(name, "node_end", latency_s=round(dt, 3), tokens=tok, cost_usd=round(cost, 6))
            return out
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        wrapper.node_name = name
        return wrapper
    return deco


def cfg_val(cfg: dict, key: str, default=None):
    return (cfg or {}).get("configurable", {}).get(key, default)

