from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ScheduledTask, TaskExecution
from app.schemas import TaskCreate, TaskUpdate

REGISTERED_TASK_TYPES: dict[str, dict[str, str]] = {
    "NEWS_REFRESH": {"label": "AI资讯更新", "handler": "news_handler"},
}

STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"


class TaskError(Exception):
    pass


class TaskNotFoundError(TaskError, LookupError):
    pass


class TaskTypeConflictError(TaskError, ValueError):
    pass


class UnknownTaskTypeError(TaskError, ValueError):
    pass


def list_registered_types() -> list[dict[str, str]]:
    return [
        {"task_type": key, "label": value["label"]}
        for key, value in REGISTERED_TASK_TYPES.items()
    ]


def list_tasks(session: Session) -> list[ScheduledTask]:
    return list(session.scalars(select(ScheduledTask).order_by(ScheduledTask.id)))


def get_task(session: Session, task_id: int) -> ScheduledTask:
    task = session.get(ScheduledTask, task_id)
    if task is None:
        raise TaskNotFoundError("任务不存在")
    return task


def create_task(session: Session, payload: TaskCreate) -> ScheduledTask:
    if payload.task_type not in REGISTERED_TASK_TYPES:
        raise UnknownTaskTypeError("未注册的任务类型")
    task = ScheduledTask(
        name=payload.name,
        task_type=payload.task_type,
        schedule_type=payload.schedule_type,
        schedule_config=payload.schedule_config,
        enabled=payload.enabled,
    )
    session.add(task)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise TaskTypeConflictError("该任务类型已存在") from exc
    session.refresh(task)
    return task


def update_task(session: Session, task_id: int, payload: TaskUpdate) -> ScheduledTask:
    task = get_task(session, task_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(task, key, value)
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: int) -> None:
    task = get_task(session, task_id)
    session.delete(task)
    session.commit()


def set_enabled(session: Session, task_id: int, enabled: bool) -> ScheduledTask:
    task = get_task(session, task_id)
    task.enabled = enabled
    session.commit()
    session.refresh(task)
    return task


def create_execution(session: Session, task_id: int) -> TaskExecution:
    get_task(session, task_id)
    execution = TaskExecution(
        task_id=task_id,
        run_id=uuid.uuid4().hex,
        status=STATUS_PENDING,
    )
    session.add(execution)
    session.commit()
    session.refresh(execution)
    return execution


def update_execution(
    session: Session,
    run_id: str,
    *,
    status: str | None = None,
    result: dict | None = None,
    error_message: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> TaskExecution:
    execution = session.scalar(select(TaskExecution).where(TaskExecution.run_id == run_id))
    if execution is None:
        raise TaskNotFoundError("执行记录不存在")
    now = datetime.now(timezone.utc)
    if started:
        execution.started_at = now
        execution.status = STATUS_RUNNING
    if status is not None:
        execution.status = status
    if result is not None:
        execution.result = result
    if error_message is not None:
        execution.error_message = error_message
    if finished:
        execution.finished_at = now
    session.commit()
    session.refresh(execution)
    return execution


def list_executions(session: Session, task_id: int, limit: int = 50) -> list[TaskExecution]:
    get_task(session, task_id)
    stmt = (
        select(TaskExecution)
        .where(TaskExecution.task_id == task_id)
        .order_by(TaskExecution.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
