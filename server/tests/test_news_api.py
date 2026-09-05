from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import News, NewsDailyRank
from app.news.scorer import shanghai_today
from http_client import api_client


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _seed_hot_row() -> int:
    today = shanghai_today()
    suffix = uuid4().hex
    session = session_scope()
    try:
        next_all = (
            session.scalar(
                select(func.coalesce(func.max(NewsDailyRank.rank), 0)).where(
                    NewsDailyRank.rank_date == today,
                    NewsDailyRank.category == "all",
                )
            )
            or 0
        ) + 1
        next_ai = (
            session.scalar(
                select(func.coalesce(func.max(NewsDailyRank.rank), 0)).where(
                    NewsDailyRank.rank_date == today,
                    NewsDailyRank.category == "ai",
                )
            )
            or 0
        ) + 1
        news = News(
            title="Step6 Hot Item",
            summary="摘要",
            content=None,
            url=f"https://example.com/news-step6-{suffix}",
            source="TestSource",
            category="ai",
            published_at=datetime.now(timezone.utc),
            importance_score=8,
            heat_score=88.5,
            content_hash=f"hash-step6-{suffix}",
        )
        session.add(news)
        session.flush()
        session.add(
            NewsDailyRank(
                news_id=news.id,
                rank_date=today,
                category="all",
                rank=next_all,
                score=88.5,
            )
        )
        session.add(
            NewsDailyRank(
                news_id=news.id,
                rank_date=today,
                category="ai",
                rank=next_ai,
                score=88.5,
            )
        )
        session.commit()
        return news.id
    finally:
        session.close()


def test_news_api_requires_login():
    reset_app_state()
    get_settings(load_file=True)
    anon = TestClient(create_app(load_file=True, ensure_default=True))
    assert anon.get("/api/news/hot").status_code == 401
    assert anon.get("/api/news/settings").status_code == 401


def test_hot_invalid_category_400():
    with _client() as client:
        res = client.get("/api/news/hot", params={"category": "sports"})
        assert res.status_code == 400, res.text


def test_hot_structure_and_limit():
    news_id = _seed_hot_row()
    with _client() as client:
        res = client.get("/api/news/hot")
        assert res.status_code == 200, res.text
        body = res.json()
        assert "date" in body
        assert body["category"] == "all"
        assert isinstance(body["items"], list)
        assert len(body["items"]) <= 20
        assert any(item["id"] == news_id for item in body["items"])
        item = next(i for i in body["items"] if i["id"] == news_id)
        assert item["rank"] >= 1
        assert item["title"]
        assert "heat_score" in item


def test_settings_put_get_and_min_one_category():
    with _client() as client:
        empty = client.put("/api/news/settings", json={"enabled_categories": []})
        assert empty.status_code == 400, empty.text

        bad = client.put(
            "/api/news/settings",
            json={"enabled_categories": ["ai", "sports"]},
        )
        assert bad.status_code == 400, bad.text

        put = client.put(
            "/api/news/settings",
            json={"enabled_categories": ["ai", "technology"]},
        )
        assert put.status_code == 200, put.text
        assert put.json()["enabled_categories"] == ["ai", "technology"]

        got = client.get("/api/news/settings")
        assert got.status_code == 200, got.text
        assert got.json()["enabled_categories"] == ["ai", "technology"]

        # restore default for other tests
        client.put(
            "/api/news/settings",
            json={"enabled_categories": ["technology", "ai", "finance"]},
        )


def test_news_detail_allows_empty_content():
    suffix = uuid4().hex
    session = session_scope()
    try:
        news = News(
            title="Step6 Detail",
            summary="摘要",
            content=None,
            url=f"https://example.com/news-detail-{suffix}",
            source="TestSource",
            category="ai",
            published_at=datetime.now(timezone.utc),
            importance_score=5,
            heat_score=10.0,
            content_hash=f"hash-detail-{suffix}",
        )
        session.add(news)
        session.commit()
        news_id = news.id
    finally:
        session.close()
    with _client() as client:
        res = client.get(f"/api/news/{news_id}")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["id"] == news_id
        assert body["content"] is None
        assert body["url"]
        assert body["summary"]
