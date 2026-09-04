from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.db import session_scope
from app.models import ScheduledTask
from app.services import task_service as ts
from app.worker.handlers import HANDLERS
from app.worker.queue import acquire_task_lock, create_redis, redis_settings, release_task_lock
from app.worker import QUEUE_NAME

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_START_S = 1.0
SKIP_MESSAGE = "同类型任务正在执行，已跳过"


async def process_task(ctx: dict, payload: dict) -> None:
    run_id = payload["run_id"]
    task_id = payload["task_id"]
    task_type = payload["task_type"]
    redis = ctx.get("redis")
    own_redis = redis is None
    if own_redis:
        redis = await create_redis()
    locked = False
    session = session_scope()
    try:
        locked = await acquire_task_lock(redis, task_type)
        if not locked:
            ts.update_execution(
                session,
                run_id,
                status=ts.STATUS_FAILED,
                error_message=SKIP_MESSAGE,
                finished=True,
            )
            logger.info(
                "task skipped task_id=%s run_id=%s task_type=%s",
                task_id,
                run_id,
                task_type,
            )
            return
        ts.update_execution(session, run_id, started=True)
        handler = HANDLERS.get(task_type)
        if handler is None:
            raise ValueError(f"未知 task_type: {task_type}")
        result = None
        last_exc: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                result = handler(payload)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "task attempt %s/%s failed task_id=%s run_id=%s task_type=%s err=%s",
                    attempt + 1,
                    MAX_ATTEMPTS,
                    task_id,
                    run_id,
                    task_type,
                    exc,
                )
                if attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(BACKOFF_START_S * (2**attempt))
        if last_exc is not None:
            ts.update_execution(
                session,
                run_id,
                status=ts.STATUS_FAILED,
                error_message=str(last_exc),
                finished=True,
            )
            logger.exception(
                "task failed task_id=%s run_id=%s task_type=%s",
                task_id,
                run_id,
                task_type,
            )
            return
        ts.update_execution(
            session,
            run_id,
            status=ts.STATUS_SUCCESS,
            result=result,
            finished=True,
        )
        task = session.get(ScheduledTask, task_id)
        if task is not None:
            task.last_run_at = datetime.now(timezone.utc)
            session.commit()
        logger.info(
            "task done task_id=%s run_id=%s task_type=%s status=SUCCESS",
            task_id,
            run_id,
            task_type,
        )
    except Exception as exc:
        ts.update_execution(
            session,
            run_id,
            status=ts.STATUS_FAILED,
            error_message=str(exc),
            finished=True,
        )
        logger.exception(
            "task failed task_id=%s run_id=%s task_type=%s",
            task_id,
            run_id,
            task_type,
        )
    finally:
        if locked:
            await release_task_lock(redis, task_type)
        if own_redis:
            await redis.aclose()
        session.close()


class WorkerSettings:
    functions = [process_task]
    redis_settings = redis_settings()
    queue_name = QUEUE_NAME
    retry_jobs = False
