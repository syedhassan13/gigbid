"""Arq worker (Redis). Each saved search runs on the configured schedule; the pipeline is
synced every 10 minutes. Without Redis the API runs the same tasks in an embedded loop.

    arq worker.main.WorkerSettings
"""
from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from agent.settings import config
from apps.api import db
from worker import tasks


async def job_analyse(ctx, user_id: str, job_id: str, force_bid: bool = False):
    return await tasks.analyse_job(user_id, job_id, force_bid)


async def job_resume_bid(ctx, user_id: str, thread_id: str, decision: dict):
    return await tasks.resume_bid(user_id, thread_id, decision)


async def job_resume_conv(ctx, user_id: str, thread_id: str, decision: dict):
    return await tasks.resume_conversation(user_id, thread_id, decision)


async def job_scout(ctx, user_id: str):
    return await tasks.scout_user(user_id)


async def scheduled_scout(ctx):
    with db.engine.connect() as c:
        uids = [r[0] for r in c.execute(select(db.users.c.id).where(db.users.c.persona.is_not(None)))]
    for uid in uids:
        await ctx["redis"].enqueue_job("job_scout", uid, _job_id=f"scout:{uid}:{int(__import__('time').time() // 3600)}")


async def scheduled_sync(ctx):
    await tasks.tick_all()


async def startup(ctx):
    db.init()


interval = config()["scout"]["interval_minutes"]
hours = set(range(0, 24, max(1, interval // 60)))


class WorkerSettings:
    functions = [job_analyse, job_resume_bid, job_resume_conv, job_scout]
    cron_jobs = [cron(scheduled_scout, hour=hours, minute=0, unique=True), cron(scheduled_sync, minute=set(range(0, 60, 10)), unique=True)]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))
    on_startup = startup
    max_jobs = 4
    job_timeout = 900
