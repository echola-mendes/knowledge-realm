from __future__ import annotations

from app.models import TaskExecution
from app.services import task_service as ts
from app.worker.queue import QueueUnavailableError, enqueue


async def enqueue_task(session, task_id: int) -> TaskExecution:
    task = ts.get_task(session, task_id)
    execution = ts.create_execution(session, task_id)
    payload = {
        "task_id": task.id,
        "task_type": task.task_type,
        "run_id": execution.run_id,
    }
    try:
        await enqueue(payload)
    except QueueUnavailableError:
        ts.update_execution(
            session,
            execution.run_id,
            status=ts.STATUS_FAILED,
            error_message="Redis 不可用，无法入队定时任务",
            finished=True,
        )
        raise
    return execution
