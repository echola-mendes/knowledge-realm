"""TRAVEL-BOOK-1：预订 Agent / HITL / 落库 / 限流 / 权限测试。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import master as master_mod
from app.booking_agent import (
    booking_initial_state,
    book_flight_tool,
    book_hotel_tool,
    build_booking_graph,
    cancel_booking_tool,
    list_bookings_tool,
    reset_booking_graph,
)
from app.models import BookingRecord, User
from app.travel import rate_limit


def _user(session: Session) -> User:
    user = User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x")
    session.add(user)
    session.commit()
    return user

@pytest.fixture
def session():
    from app.db import session_scope

    s = session_scope()
    try:
        yield s
    finally:
        s.close()

# ---------- 工具层 ----------


def test_book_flight_without_hitl_no_db_row(session: Session):
    user = _user(session)
    out = book_flight_tool(
        session,
        user.id,
        {"flight_no": "MU5101", "depart_date": "2026-09-10"},
        confirmed=None,
    )
    assert out["kind"] == "pending"
    assert out["pending_action"]["tool"] == "book_flight"
    rows = session.scalars(select(BookingRecord).where(BookingRecord.user_id == user.id)).all()
    assert not rows


def test_book_flight_confirmed_creates_record(session: Session):
    user = _user(session)
    out = book_flight_tool(
        session,
        user.id,
        {"flight_no": "MU5101", "depart_date": "2026-09-10"},
        confirmed=True,
    )
    assert out["kind"] == "booked"
    row = session.scalar(select(BookingRecord).where(BookingRecord.user_id == user.id))
    assert row is not None
    assert row.kind == "flight"
    assert row.status == "pending"
    assert row.user_id == user.id
    assert row.payload["flight_no"] == "MU5101"


def test_book_hotel_confirmed_creates_record(session: Session):
    user = _user(session)
    out = book_hotel_tool(
        session,
        user.id,
        {"hotel_name": "希尔顿", "check_in": "2026-09-10", "check_out": "2026-09-12"},
        confirmed=True,
    )
    assert out["kind"] == "booked"
    row = session.scalar(select(BookingRecord).where(BookingRecord.user_id == user.id))
    assert row is not None
    assert row.kind == "hotel"


def test_list_bookings_isolation(session: Session):
    user_a = _user(session)
    user_b = _user(session)
    record_a = BookingRecord(
        user_id=user_a.id,
        kind="flight",
        vendor="flyai",
        status="pending",
    )
    record_b = BookingRecord(
        user_id=user_b.id,
        kind="hotel",
        vendor="flyai",
        status="pending",
    )
    session.add_all([record_a, record_b])
    session.commit()

    out_a = list_bookings_tool(session, user_a.id)
    assert len(out_a["items"]) == 1
    assert out_a["items"][0]["kind"] == "flight"

    out_b = list_bookings_tool(session, user_b.id)
    assert len(out_b["items"]) == 1
    assert out_b["items"][0]["kind"] == "hotel"


def test_cancel_booking_requires_hitl_then_updates(session: Session):
    user = _user(session)
    record = BookingRecord(
        user_id=user.id,
        kind="flight",
        vendor="flyai",
        status="pending",
    )
    session.add(record)
    session.commit()

    # 未确认不应改库
    out_pending = cancel_booking_tool(
        session, user.id, {"booking_id": str(record.id)}, confirmed=None
    )
    assert out_pending["kind"] == "pending"
    session.refresh(record)
    assert record.status == "pending"

    # 确认后取消
    out_cancel = cancel_booking_tool(
        session, user.id, {"booking_id": str(record.id)}, confirmed=True
    )
    assert out_cancel["kind"] == "cancelled"
    assert out_cancel["status"] == "cancelled"
    session.refresh(record)
    assert record.status == "cancelled"


def test_cancel_booking_cross_user_not_found(session: Session):
    user_a = _user(session)
    user_b = _user(session)
    record = BookingRecord(user_id=user_a.id, kind="flight", vendor="flyai", status="pending")
    session.add(record)
    session.commit()
    out = cancel_booking_tool(
        session, user_b.id, {"booking_id": str(record.id)}, confirmed=True
    )
    assert out["kind"] == "error"


# ---------- 限流 ----------


def test_rate_limit_31st_write_raises():
    rate_limit.reset_rate_limit()
    user_id = uuid.uuid4()
    for _ in range(30):
        rate_limit.check_write_rate(user_id)
    with pytest.raises(rate_limit.RateLimitedError):
        rate_limit.check_write_rate(user_id)


# ---------- booking_agent 图 ----------


def _config(session: Session, user_id: uuid.UUID, emit=None):
    return {
        "configurable": {
            "session": session,
            "user_id": user_id,
            "emit": emit or (lambda x: None),
        }
    }


def test_booking_agent_asks_for_confirmation(monkeypatch, session: Session):
    monkeypatch.setattr(
        "app.booking_agent._reason_llm",
        lambda state: {"action": "book_flight", "params": {"flight_no": "MU5101"}},
    )
    user = _user(session)
    events: list[dict] = []
    out = build_booking_graph().invoke(
        booking_initial_state("订这个航班", user_id=user.id),
        config=_config(session, user.id, events.append),
    )
    assert out["answer"].startswith("请确认")
    assert out["pending_action"]["tool"] == "book_flight"
    assert any(e["type"] == "hitl" for e in events)
    rows = session.scalars(select(BookingRecord).where(BookingRecord.user_id == user.id)).all()
    assert not rows
    reset_booking_graph()


def test_booking_agent_confirms_then_books(monkeypatch, session: Session):
    monkeypatch.setattr(
        "app.booking_agent._reason_llm",
        lambda state: {"action": "book_flight", "params": {"flight_no": "MU5101"}},
    )
    user = _user(session)
    # 第一轮：产生 pending
    out1 = build_booking_graph().invoke(
        booking_initial_state("订这个航班", user_id=user.id),
        config=_config(session, user.id),
    )
    assert out1["pending_action"] is not None

    # 第二轮：confirmed 落库
    out2 = build_booking_graph().invoke(
        booking_initial_state(
            "确认",

            user_id=user.id,
            hitl_confirm=True,
            pending_action=out1["pending_action"],
        ),
        config=_config(session, user.id),
    )
    assert out2["answer"].startswith("预订已提交")
    row = session.scalar(select(BookingRecord).where(BookingRecord.user_id == user.id))
    assert row is not None
    reset_booking_graph()


def test_booking_agent_list_query(monkeypatch, session: Session):
    monkeypatch.setattr("app.booking_agent._reason_llm", lambda state: {"action": "list"})
    user = _user(session)
    record = BookingRecord(user_id=user.id, kind="flight", vendor="flyai", status="pending")
    session.add(record)
    session.commit()
    out = build_booking_graph().invoke(
        booking_initial_state("我的预订", user_id=user.id),
        config=_config(session, user.id),
    )
    assert "航班" in out["answer"] or "预订" in out["answer"]
    reset_booking_graph()


# ---------- Master 路由 ----------


def test_master_booking_routes_to_booking_agent(monkeypatch):
    import app.booking_agent as booking_mod

    seen: dict = {}

    class FakeBookingGraph:
        def invoke(self, state, config=None):
            seen["state"] = state
            seen["config"] = config
            return {"answer": "预订助手答案", "pending_action": None}

    def _intent_of(label: str):
        return lambda query, *, task="agent", history_tail=None: label

    monkeypatch.setattr(master_mod, "classify_intent", lambda *a, **k: "booking")
    monkeypatch.setattr("app.booking_agent.build_booking_graph", lambda: FakeBookingGraph())
    out = master_mod.build_master_graph().invoke(
        master_mod.master_initial_state("帮我订机票"),
        config={
            "configurable": {
                "thread_id": f"master-{uuid.uuid4()}",
                "session": object(),
                "user_id": uuid.uuid4(),
            }
        },
    )
    assert out["answer"] == "预订助手答案"
    assert out["intent"] == "booking"
    assert seen["state"]["messages"][-1] == {"role": "user", "content": "帮我订机票"}


def test_agent_router_booking_not_500(monkeypatch):
    class FakeBookingGraph:
        def invoke(self, state, config=None):
            return {"answer": "预订假答案", "pending_action": None}

    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", lambda *a, **k: "booking")
    monkeypatch.setattr("app.booking_agent.build_booking_graph", lambda: FakeBookingGraph())
    from app.main import reset_app_state
    from http_client import api_client

    reset_app_state()
    client = api_client()
    try:
        kb = client.post("/api/knowledge-bases", json={"name": f"Book-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "agent", "query": "帮我订机票", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "预订假答案"
        assert body["intent"] == "booking"
    finally:
        reset_app_state()


def test_list_bookings_emits_booking_data(monkeypatch, session):
    monkeypatch.setattr("app.booking_agent._reason_llm", lambda state: {"action": "list"})
    user = _user(session)
    record = BookingRecord(user_id=user.id, kind="flight", vendor="flyai", status="pending")
    session.add(record)
    session.commit()
    events: list[dict] = []
    out = build_booking_graph().invoke(
        booking_initial_state("我的预订", user_id=user.id),
        config=_config(session, user.id, events.append),
    )
    assert any(e["type"] == "booking_data" for e in events)
    assert len(out.get("bookings") or []) == 1
    reset_booking_graph()


def test_agent_router_rate_limit_429(monkeypatch):
    from app.travel import rate_limit

    rate_limit.reset_rate_limit()
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", lambda *a, **k: "booking")
    monkeypatch.setattr(
        "app.booking_agent._reason_llm",
        lambda state: {"action": "book_flight", "params": {"flight_no": "MU5101", "depart_date": "2026-09-10"}},
    )
    monkeypatch.setattr("app.routers.master.refresh_conversation_summary", lambda *a, **k: None)
    from app.main import reset_app_state
    from http_client import api_client

    reset_app_state()
    client = api_client()
    try:
        kb = client.post("/api/knowledge-bases", json={"name": f"RL-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = kb["id"]
        convo_id = None
        for _ in range(30):
            if convo_id is None:
                r0 = client.post(
                    "/api/agent",
                    json={"task": "agent", "query": "订MU5101", "knowledge_base_id": kb_id},
                )
            else:
                r0 = client.post(
                    "/api/agent",
                    json={
                        "task": "agent",
                        "query": "再订MU5101",
                        "knowledge_base_id": kb_id,
                        "conversation_id": convo_id,
                    },
                )
            assert r0.status_code == 200
            convo_id = r0.json()["conversation_id"]
            r1 = client.post(
                "/api/agent",
                json={
                    "task": "agent",
                    "query": "确认",
                    "knowledge_base_id": kb_id,
                    "conversation_id": convo_id,
                    "hitl_confirm": True,
                },
            )
            assert r1.status_code == 200
        r0 = client.post(
            "/api/agent",
            json={"task": "agent", "query": "再订MU5101", "knowledge_base_id": kb_id, "conversation_id": convo_id},
        )
        assert r0.status_code == 200
        r1 = client.post(
            "/api/agent",
            json={
                "task": "agent",
                "query": "确认",
                "knowledge_base_id": kb_id,
                "conversation_id": convo_id,
                "hitl_confirm": True,
            },
        )
        assert r1.status_code == 429
    finally:
        reset_app_state()
        reset_booking_graph()
