from __future__ import annotations

from app.db import session_scope
from app.scheduler.executor import enqueue_task


async def run_news_refresh(task_id: int) -> None:
    session = session_scope()
    try:
        await enqueue_task(session, task_id)
    finally:
        session.close()
