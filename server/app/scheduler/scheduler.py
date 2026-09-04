from __future__ import annotations

import logging
from datetime import timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.db import session_scope
from app.jobs.news_job import run_news_refresh
from app.models import ScheduledTask
from app.services.task_service import list_tasks

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

JOB_CALLBACKS = {
    "NEWS_REFRESH": run_news_refresh,
}


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def _trigger_for(task: ScheduledTask):
    config = dict(task.schedule_config or {})
    if task.schedule_type == "INTERVAL":
        return IntervalTrigger(**config)
    if task.schedule_type == "CRON":
        return CronTrigger(**config)
    raise ValueError(f"未知 schedule_type: {task.schedule_type}")


def _callback_for(task: ScheduledTask):
    callback = JOB_CALLBACKS.get(task.task_type)
    if callback is None:
        raise ValueError(f"未知 task_type: {task.task_type}")
    return callback


def reload_jobs(session: Session | None = None) -> None:
    scheduler = get_scheduler()
    scheduler.remove_all_jobs()
    own_session = session is None
    if own_session:
        session = session_scope()
    try:
        for task in list_tasks(session):
            if not task.enabled:
                continue
            scheduler.add_job(
                _callback_for(task),
                trigger=_trigger_for(task),
                id=f"task-{task.id}",
                kwargs={"task_id": task.id},
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            job = scheduler.get_job(f"task-{task.id}")
            if job and job.next_run_time:
                next_run = job.next_run_time
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
                task.next_run_at = next_run.astimezone(timezone.utc)
        session.commit()
        logger.info("scheduler jobs: %s", [j.id for j in scheduler.get_jobs()])
    finally:
        if own_session:
            session.close()


def start_scheduler() -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    reload_jobs()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
