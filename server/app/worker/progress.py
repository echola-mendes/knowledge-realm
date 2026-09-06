from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache

logger = logging.getLogger(__name__)

PROGRESS_KEY_PREFIX = "task:progress:"
PROGRESS_TTL_SECONDS = 6 * 3600


def progress_key(run_id: str) -> str:
    return f"{PROGRESS_KEY_PREFIX}{run_id}"


@lru_cache(maxsize=1)
def _client():
    import redis as redis_lib

    from app.config import get_settings

    return redis_lib.Redis.from_url(get_settings().redis_url, decode_responses=True)


def write_progress(run_id: str, stage: str, *, done: int | None = None, total: int | None = None) -> None:
    payload: dict = {"stage": stage, "updated_at": datetime.now(timezone.utc).isoformat()}
    if done is not None:
        payload["done"] = int(done)
    if total is not None:
        payload["total"] = int(total)
    try:
        _client().set(progress_key(run_id), json.dumps(payload), ex=PROGRESS_TTL_SECONDS)
    except Exception:  # noqa: BLE001 — 进度上报失败不影响任务本身
        logger.debug("write_progress failed run_id=%s stage=%s", run_id, stage)


def read_progress(run_id: str) -> dict | None:
    try:
        raw = _client().get(progress_key(run_id))
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class PipelineProgress:
    """Worker 传入新闻管线的进度上报器；run_id 为空时退化为 no-op。"""

    def __init__(self, run_id: str | None) -> None:
        self._run_id = run_id

    def stage(self, stage: str, *, done: int | None = None, total: int | None = None) -> None:
        if not self._run_id:
            return
        write_progress(self._run_id, stage, done=done, total=total)


def make_progress(run_id: object | None) -> PipelineProgress:
    return PipelineProgress(run_id if isinstance(run_id, str) and run_id else None)
