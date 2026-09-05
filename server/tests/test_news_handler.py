from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import session_scope
from app.main import reset_app_state
from app.config import get_settings
from app.models import NewsSettings, TaskExecution
from app.services import task_service as ts
from app.worker.handlers.news_handler import handle_news_refresh
from app.worker.settings import process_task
from http_client import api_client


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


def _set_enabled_categories(categories: list[str]) -> None:
    session = session_scope()
    try:
        row = session.scalar(select(NewsSettings).order_by(NewsSettings.id.asc()).limit(1))
        assert row is not None
        row.enabled_categories = categories
        session.commit()
    finally:
        session.close()


def _ensure_news_task() -> dict:
    reset_app_state()
    get_settings(load_file=True)
    with api_client() as client:
        for row in client.get("/api/tasks").json():
            if row["task_type"] == "NEWS_REFRESH":
                return row
        created = client.post(
            "/api/tasks",
            json={
                "name": "AI资讯更新",
                "task_type": "NEWS_REFRESH",
                "schedule_type": "INTERVAL",
                "schedule_config": {"minutes": 30},
                "enabled": True,
            },
        )
        assert created.status_code == 201, created.text
        return created.json()


def test_handler_ai_only_does_not_collect_other_categories(monkeypatch):
    _set_enabled_categories(["ai"])
    seen_categories: list[str] = []

    def fake_collect(sources, *, timeout=None):
        seen_categories.extend(s.category for s in sources)
        return []

    monkeypatch.setattr("app.news.service.collect_sources", fake_collect)
    result = handle_news_refresh({})

    assert seen_categories
    assert set(seen_categories) == {"ai"}
    assert "technology" not in seen_categories
    assert "finance" not in seen_categories
    assert result["categories"] == ["ai"]
    assert "news_pipeline_pending" not in result
    for key in ("fetched", "saved", "summarized", "failed", "skipped_dup"):
        assert key in result


def test_process_task_writes_counter_result(monkeypatch):
    _set_enabled_categories(["ai"])
    monkeypatch.setattr(
        "app.news.service.collect_sources",
        lambda sources, *, timeout=None: [],
    )
    task = _ensure_news_task()
    session = session_scope()
    try:
        execution = ts.create_execution(session, task["id"])
        run_id = execution.run_id
    finally:
        session.close()

    asyncio.run(
        process_task(
            {"redis": FakeRedis()},
            {
                "task_id": task["id"],
                "task_type": task["task_type"],
                "run_id": run_id,
            },
        )
    )

    session = session_scope()
    try:
        row = session.scalar(select(TaskExecution).where(TaskExecution.run_id == run_id))
        assert row is not None
        assert row.status == ts.STATUS_SUCCESS
        assert row.result is not None
        assert "news_pipeline_pending" not in row.result
        assert row.result.get("categories") == ["ai"]
        for key in ("fetched", "saved", "summarized", "failed", "skipped_dup"):
            assert key in row.result
    finally:
        session.close()
