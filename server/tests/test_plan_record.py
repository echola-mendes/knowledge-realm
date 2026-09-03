"""行程单落库与 GET /api/plans。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import PlanRecord, User
from app.plan_agent import persist_plan_record
from app.user import ensure_default_user
from http_client import api_client


@pytest.fixture
def session():
    s = session_scope()
    try:
        yield s
    finally:
        s.close()


def _user(session: Session) -> User:
    user = User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x")
    session.add(user)
    session.commit()
    return user


def test_persist_plan_record_without_minio(session: Session):
    user = _user(session)
    record = persist_plan_record(
        session,
        user.id,
        conversation_id=None,
        params={"origin": "上海", "destination": "北京", "depart_date": "2026-10-01"},
        plan={"options": [{"id": "A"}], "recommendation": {"option_id": "A", "reason": "便宜"}},
        plan_html={"html": "<html></html>", "note": "MinIO 未配置"},
    )
    assert record is not None
    assert record.title == "上海→北京"
    assert record.url is None
    assert record.minio_key is None
    rows = session.scalars(select(PlanRecord).where(PlanRecord.user_id == user.id)).all()
    assert len(rows) == 1


def test_list_plans_isolation():
    with api_client() as client:
        me = client.get("/api/auth/me").json()
        me_id = uuid.UUID(me["id"])
        session = session_scope()
        try:
            ensure_default_user(session)
            other = _user(session)
            persist_plan_record(
                session,
                me_id,
                conversation_id=None,
                params={"origin": "杭", "destination": "深"},
                plan={},
                plan_html={"url": "https://example.com/a", "key": "plans/a.html"},
            )
            other_rec = persist_plan_record(
                session,
                other.id,
                conversation_id=None,
                params={"origin": "广", "destination": "成"},
                plan={},
                plan_html={},
            )
            assert other_rec is not None
            other_id = other_rec.id
        finally:
            session.close()

        res = client.get("/api/plans")
        assert res.status_code == 200
        data = res.json()
        titles = {row["title"] for row in data}
        assert "杭→深" in titles
        assert "广→成" not in titles
        assert all(row["title"] != "广→成" for row in data)
        assert all("status" not in row for row in data)
        assert all(row.get("trip_type") in {"business", "leisure", "study", "other"} for row in data)

        blocked = client.get(f"/api/plans/{other_id}")
        assert blocked.status_code == 404


def test_persist_infers_trip_type_and_nights(session: Session):
    user = _user(session)
    record = persist_plan_record(
        session,
        user.id,
        conversation_id=None,
        params={
            "origin": "深圳",
            "destination": "北京",
            "depart_date": "2026-09-08",
            "return_date": "2026-09-10",
            "trip_type": "出差开会",
        },
        plan={},
        plan_html={},
    )
    assert record is not None
    assert record.trip_type == "business"
    assert record.nights == 2


def test_infer_trip_type_keywords():
    from app.travel.params_parse import infer_trip_type, nights_from_params

    assert infer_trip_type("下周去上海旅游") == "leisure"
    assert infer_trip_type("去杭州参加培训") == "study"
    assert infer_trip_type("去成都") == "other"
    assert nights_from_params({"depart_date": "2026-09-08", "return_date": "2026-09-10"}) == 2
