from __future__ import annotations

from dataclasses import replace

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from redis.exceptions import RedisError

from app.config import get_settings
from app.worker import LOCK_TTL_SECONDS, QUEUE_NAME

PROCESS_TASK = "process_task"


class QueueUnavailableError(RuntimeError):
    pass


def redis_settings(*, retries: int | None = None) -> RedisSettings:
    try:
        settings = RedisSettings.from_dsn(get_settings().redis_url)
    except RuntimeError as exc:
        raise QueueUnavailableError("Redis 不可用，无法入队定时任务") from exc
    if retries is None:
        return settings
    return replace(settings, conn_retries=retries, conn_retry_delay=0)


async def create_redis() -> ArqRedis:
    try:
        redis = await create_pool(redis_settings(retries=1), default_queue_name=QUEUE_NAME)
        await redis.ping()
        return redis
    except QueueUnavailableError:
        raise
    except (OSError, RedisError, ConnectionError, TimeoutError) as exc:
        raise QueueUnavailableError("Redis 不可用，无法入队定时任务") from exc


async def enqueue(payload: dict) -> str | None:
    redis = await create_redis()
    try:
        job = await redis.enqueue_job(PROCESS_TASK, payload)
        if job is None:
            raise QueueUnavailableError("任务入队失败")
        return job.job_id
    finally:
        await redis.aclose()


async def acquire_task_lock(redis, task_type: str) -> bool:
    return bool(await redis.set(f"task:lock:{task_type}", "1", nx=True, ex=LOCK_TTL_SECONDS))


async def release_task_lock(redis, task_type: str) -> None:
    await redis.delete(f"task:lock:{task_type}")
