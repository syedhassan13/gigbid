"""Runtime: durable checkpointer (Postgres in compose/deploy, SQLite locally), the memory
store, both compiled graphs, and helpers to start / stream / resume / inspect threads.
Used by the API, the worker and the eval runners."""
from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any, AsyncIterator

from langgraph.types import Command

from agent.graphs import bid_graph, conversation_graph
from agent.marketplace_port import MarketplacePort
from agent.memory.store import get_store
from agent.settings import HOME
from agent.tracing import current_trace_id, start_run


class Runtime:
    def __init__(self):
        self._stack = AsyncExitStack()
        self.checkpointer = None
        self.store = None
        self.bid = None
        self.conv = None

    async def start(self) -> "Runtime":
        url = os.getenv("DATABASE_URL", "")
        if url.startswith("postgres"):
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            self.checkpointer = await self._stack.enter_async_context(AsyncPostgresSaver.from_conn_string(url))
        else:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            p = HOME / "var" / "checkpoints.db"
            p.parent.mkdir(parents=True, exist_ok=True)
            self.checkpointer = await self._stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(p)))
        await self.checkpointer.setup()
        self.store = get_store()
        self.bid = bid_graph.build(self.checkpointer, self.store)
        self.conv = conversation_graph.build(self.checkpointer, self.store)
        return self

    async def stop(self) -> None:
        await self._stack.aclose()

    def graph(self, kind: str):
        return self.bid if kind == "bid" else self.conv

    @staticmethod
    def config(thread_id: str, port: MarketplacePort, persona: str, user_prefs: dict | None = None, trace_id: str = "") -> dict:
        return {"configurable": {"thread_id": thread_id, "port": port, "persona": persona, "user_prefs": user_prefs or {}},
                "run_name": f"gigbid:{thread_id}", "metadata": {"trace_id": trace_id, "persona": persona},
                "recursion_limit": 60}

    async def stream(self, kind: str, thread_id: str, inp: Any, port: MarketplacePort, persona: str, user_prefs: dict | None = None,
                     trace_id: str | None = None) -> AsyncIterator[dict]:
        """Yields {"type": "update"|"interrupt"|"done", ...}. `inp` is the initial state or a Command(resume=...)."""
        usage = start_run(trace_id)
        cfg = self.config(thread_id, port, persona, user_prefs, usage.trace_id)
        async for mode, chunk in self.graph(kind).astream(inp, cfg, stream_mode=["updates", "custom"]):
            if mode == "updates":
                for node, upd in chunk.items():
                    if node == "__interrupt__":
                        yield {"type": "interrupt", "thread_id": thread_id, "payload": [i.value for i in upd]}
                    else:
                        yield {"type": "update", "node": node, "thread_id": thread_id,
                               "status": (upd or {}).get("status"), "trace": (upd or {}).get("trace", [])[-2:] if upd else []}
        st = await self.graph(kind).aget_state(cfg)
        yield {"type": "done", "thread_id": thread_id, "status": st.values.get("status"), "usage": usage.snapshot(),
               "next": list(st.next), "trace_id": current_trace_id.get()}

    async def run(self, kind: str, thread_id: str, inp: Any, port: MarketplacePort, persona: str, **kw) -> dict:
        last = {}
        async for ev in self.stream(kind, thread_id, inp, port, persona, **kw):
            last = ev if ev["type"] == "done" else last
        return last

    async def resume(self, kind: str, thread_id: str, decision: dict, port: MarketplacePort, persona: str, **kw) -> dict:
        return await self.run(kind, thread_id, Command(resume=decision), port, persona, **kw)

    async def state(self, kind: str, thread_id: str) -> dict:
        st = await self.graph(kind).aget_state({"configurable": {"thread_id": thread_id}})
        interrupts = [i.value for t in st.tasks for i in (t.interrupts or [])]
        return {"values": st.values, "next": list(st.next), "interrupts": interrupts,
                "checkpoint_id": st.config["configurable"].get("checkpoint_id")}

    async def history(self, kind: str, thread_id: str) -> list[dict]:
        out = []
        async for s in self.graph(kind).aget_state_history({"configurable": {"thread_id": thread_id}}):
            out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"], "next": list(s.next),
                        "status": s.values.get("status"), "step": s.metadata.get("step") if s.metadata else None})
        return out

    async def replay(self, kind: str, thread_id: str, checkpoint_id: str, port: MarketplacePort, persona: str) -> dict:
        """Replay a job from any checkpoint (time travel) - re-executes nodes after it on a fork."""
        usage = start_run()
        cfg = self.config(thread_id, port, persona, trace_id=usage.trace_id)
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
        async for _ in self.graph(kind).astream(None, cfg, stream_mode="updates"):
            pass
        return await self.state(kind, thread_id)
