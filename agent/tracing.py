"""Per-run accounting (tokens, cost, latency per node) + PII masking for logs/traces.

One trace id flows UI -> API -> graph -> MCP servers -> audit log (header `X-Trace-Id`).
If LANGSMITH_API_KEY / LANGFUSE_* are set, LangGraph runs are also exported there;
the in-app trace (runs table) is always kept.
"""
from __future__ import annotations

import contextvars
import re
import time
import uuid
from dataclasses import dataclass, field

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_HANDLE = re.compile(r"(?i)(?:t\.me|wa\.me|telegram\.me)/\S+|@[A-Za-z0-9_]{4,}")


def mask_pii(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = _EMAIL.sub("[email]", text)
    text = _CARD.sub("[card]", text)
    text = _IBAN.sub("[iban]", text)
    text = _PHONE.sub("[phone]", text)
    return _HANDLE.sub("[handle]", text)


def mask_obj(obj):
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v) for v in obj]
    return obj


@dataclass
class RunUsage:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    per_node: dict = field(default_factory=dict)
    started: float = field(default_factory=time.time)

    def add(self, node: str, tin: int, tout: int, cost: float, latency: float, model: str) -> None:
        self.tokens_in += tin
        self.tokens_out += tout
        self.cost_usd += cost
        self.llm_calls += 1
        n = self.per_node.setdefault(node, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "calls": 0, "latency_s": 0.0, "model": model})
        n["tokens_in"] += tin
        n["tokens_out"] += tout
        n["cost_usd"] += cost
        n["calls"] += 1
        n["latency_s"] += latency

    def snapshot(self) -> dict:
        return {"trace_id": self.trace_id, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "tokens": self.tokens_in + self.tokens_out,
                "cost_usd": round(self.cost_usd, 6), "llm_calls": self.llm_calls, "per_node": self.per_node,
                "elapsed_s": round(time.time() - self.started, 3)}


current_usage: contextvars.ContextVar[RunUsage | None] = contextvars.ContextVar("current_usage", default=None)
current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_trace_id", default="")


def start_run(trace_id: str | None = None) -> RunUsage:
    u = RunUsage(trace_id=trace_id or uuid.uuid4().hex)
    current_usage.set(u)
    current_trace_id.set(u.trace_id)
    return u
