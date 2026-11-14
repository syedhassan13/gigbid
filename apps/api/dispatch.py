"""Hand work to the worker: Arq/Redis when REDIS_URL is set, else the embedded worker loop
(still outside the request: the request returns immediately with the thread id)."""
from __future__ import annotations

import asyncio
import os

from worker import tasks

_bg: set[asyncio.Task] = set()
_pool = None

FN = {"job_analyse": tasks.analyse_job, "job_resume_bid": tasks.resume_bid, "job_resume_conv": tasks.resume_conversation,
      "job_scout": tasks.scout_user}


async def dispatch(name: str, *args) -> None:
    global _pool
    if os.getenv("REDIS_URL"):
        from arq import create_pool
        from arq.connections import RedisSettings
        if _pool is None:
            _pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
        await _pool.enqueue_job(name, *args)
        return
    t = asyncio.create_task(FN[name](*args))
    _bg.add(t)
    t.add_done_callback(_bg.discard)


def worker_mode() -> str:
    return "arq" if os.getenv("REDIS_URL") else "embedded"
