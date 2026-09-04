from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.models import User
from app.scheduler.scheduler import reload_jobs
from app.scheduler.executor import enqueue_task
from app.schemas import ExecutionOut, TaskCreate, TaskOut, TaskTypeOut, TaskUpdate
from app.services import task_service as ts
from app.worker.queue import QueueUnavailableError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _http(exc: ts.TaskError) -> HTTPException:
    if isinstance(exc, ts.TaskNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ts.TaskTypeConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ts.UnknownTaskTypeError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/types", response_model=list[TaskTypeOut])
def list_types(_user: User = Depends(current_user)):
    return ts.list_registered_types()


@router.get("", response_model=list[TaskOut])
def list_tasks(session: Session = Depends(get_db), _user: User = Depends(current_user)):
    return ts.list_tasks(session)


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    body: TaskCreate,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        task = ts.create_task(session, body)
    except ts.TaskError as exc:
        raise _http(exc) from exc
    reload_jobs(session)
    return task


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        task = ts.update_task(session, task_id, body)
    except ts.TaskError as exc:
        raise _http(exc) from exc
    reload_jobs(session)
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        ts.delete_task(session, task_id)
    except ts.TaskError as exc:
        raise _http(exc) from exc
    reload_jobs(session)
    return {"ok": True}


@router.post("/{task_id}/enable", response_model=TaskOut)
def enable_task(
    task_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        task = ts.set_enabled(session, task_id, True)
    except ts.TaskError as orig:
        raise _http(orig) from orig
    reload_jobs(session)
    return task


@router.post("/{task_id}/disable", response_model=TaskOut)
def disable_task(
    task_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        task = ts.set_enabled(session, task_id, False)
    except ts.TaskError as orig:
        raise _http(orig) from orig
    reload_jobs(session)
    return task


@router.post("/{task_id}/run")
async def run_task(
    task_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        execution = await enqueue_task(session, task_id)
    except ts.TaskError as exc:
        raise _http(exc) from exc
    except QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"execution_id": execution.id, "run_id": execution.run_id}


@router.get("/{task_id}/executions", response_model=list[ExecutionOut])
def list_executions(
    task_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    try:
        return ts.list_executions(session, task_id, limit=limit)
    except ts.TaskError as exc:
        raise _http(exc) from exc
