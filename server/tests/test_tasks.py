from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.main import reset_app_state
from app.models import TaskExecution
from app.services import task_service as ts
from app.worker.handlers import HANDLERS
from app.worker.settings import SKIP_MESSAGE, process_task


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client

    return api_client()


def _news_payload() -> dict:
    return {
        "name": "AI资讯更新",
        "task_type": "NEWS_REFRESH",
        "schedule_type": "INTERVAL",
        "schedule_config": {"minutes": 30},
        "enabled": True,
    }


def _ensure_news(client: TestClient) -> dict:
    for row in client.get("/api/tasks").json():
        if row["task_type"] == "NEWS_REFRESH":
            return row
    created = client.post("/api/tasks", json=_news_payload())
    assert created.status_code == 201, created.text
    return created.json()


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


def test_task_crud_and_executions():
    with _client() as client:
        types = client.get("/api/tasks/types")
        assert types.status_code == 200
        assert any(t["task_type"] == "NEWS_REFRESH" for t in types.json())
        task = _ensure_news(client)
        task_id = task["id"]
        listed = client.get("/api/tasks")
        assert listed.status_code == 200
        assert any(t["id"] == task_id for t in listed.json())
        dup = client.post("/api/tasks", json=_news_payload())
        assert dup.status_code == 409
        renamed = client.put(f"/api/tasks/{task_id}", json={"name": "资讯刷新"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "资讯刷新"
        disabled = client.post(f"/api/tasks/{task_id}/disable")
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        enabled = client.post(f"/api/tasks/{task_id}/enable")
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True
        hist = client.get(f"/api/tasks/{task_id}/executions")
        assert hist.status_code == 200
        assert isinstance(hist.json(), list)


def test_run_enqueues_without_blocking():
    with _client() as client:
        task = _ensure_news(client)
        res = client.post(f"/api/tasks/{task['id']}/run")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("execution_id")
        assert body.get("run_id")
        rows = client.get(f"/api/tasks/{task['id']}/executions").json()
        assert rows[0]["id"] == body["execution_id"]
        assert rows[0]["status"] == "PENDING"


def test_skip_when_same_type_locked():
    with _client() as client:
        task = _ensure_news(client)
        session = session_scope()
        try:
            execution = ts.create_execution(session, task["id"])
            run_id = execution.run_id
        finally:
            session.close()
        redis = FakeRedis()
        asyncio.run(redis.set(f"task:lock:{task['task_type']}", "1", nx=True))
        asyncio.run(
            process_task(
                {"redis": redis},
                {"task_id": task["id"], "task_type": task["task_type"], "run_id": run_id},
            )
        )
        session = session_scope()
        try:
            row = session.scalar(select(TaskExecution).where(TaskExecution.run_id == run_id))
            assert row is not None
            assert row.status == ts.STATUS_FAILED
            assert row.error_message == SKIP_MESSAGE
            running = session.scalar(
                select(func.count())
                .select_from(TaskExecution)
                .where(TaskExecution.task_id == task["id"], TaskExecution.status == ts.STATUS_RUNNING)
            )
            assert running == 0
        finally:
            session.close()


def test_retry_then_failed(monkeypatch):
    calls = {"n": 0}

    def boom(_payload: dict) -> dict:
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr("app.worker.settings.BACKOFF_START_S", 0)
    monkeypatch.setitem(HANDLERS, "NEWS_REFRESH", boom)

    with _client() as client:
        task = _ensure_news(client)
        session = session_scope()
        try:
            execution = ts.create_execution(session, task["id"])
            run_id = execution.run_id
        finally:
            session.close()
        asyncio.run(
            process_task(
                {"redis": FakeRedis()},
                {"task_id": task["id"], "task_type": task["task_type"], "run_id": run_id},
            )
        )
        session = session_scope()
        try:
            row = session.scalar(select(TaskExecution).where(TaskExecution.run_id == run_id))
            assert row is not None
            assert row.status == ts.STATUS_FAILED
            assert row.error_message == "boom"
            assert calls["n"] == 3
        finally:
            session.close()
