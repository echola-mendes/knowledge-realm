"""确认方案 → booking 意图与从 plan_record 抽航班。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db import session_scope
from app.intent import classify_intent
import app.intent as intent_mod
from app.booking_agent import (
    book_flight_tool,
    build_booking_graph,
    booking_initial_state,
    reset_booking_graph,
)
from app.models import BookingRecord, PlanRecord, User
from app.plan_agent import persist_plan_record
from app.travel.plan_confirm import (
    booking_params_from_option,
    is_confirm_plan_query,
    parse_confirm_option_index,
    resolve_confirm_booking_params,
    resolve_option,
)
from sqlalchemy import select


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


def _sample_plan() -> dict:
    return {
        "options": [
            {
                "id": "opt-1",
                "label": "ZH9101 08:00",
                "segments": [
                    {
                        "type": "flight",
                        "leg": "outbound",
                        "flight_no": "ZH9101",
                        "dep_place": "深圳",
                        "arr_place": "北京",
                        "summary": "ZH9101 深圳→北京 08:00–11:10",
                    },
                    {
                        "type": "flight",
                        "leg": "return",
                        "flight_no": "CA1388",
                        "dep_place": "北京",
                        "arr_place": "深圳",
                        "summary": "CA1388 北京→深圳 19:00–22:25",
                    },
                ],
                "total_price": 1800,
            },
            {
                "id": "opt-2",
                "label": "MU5101",
                "segments": [
                    {
                        "type": "flight",
                        "leg": "outbound",
                        "flight_no": "MU5101",
                        "dep_place": "深圳",
                        "arr_place": "北京",
                    }
                ],
                "total_price": 2000,
            },
        ],
        "recommendation": {"option_id": "opt-1", "reason": "时刻合适"},
        "total_price_summary": "约 ¥1800",
    }


# ---------- plan_confirm helpers ----------


def test_parse_confirm_option_index():
    assert parse_confirm_option_index("确认方案1") == 1
    assert parse_confirm_option_index("确认P2") == 2
    assert parse_confirm_option_index("选方案 3") == 3
    assert parse_confirm_option_index("方案1确认") == 1
    assert parse_confirm_option_index("什么是方案1") is None
    assert is_confirm_plan_query("确认方案1")


def test_classify_confirm_plan_forces_booking(monkeypatch):
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "knowledge")
    assert classify_intent("确认方案1", task="agent") == "booking"
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "plan")
    assert classify_intent("确认P1", task="agent") == "booking"
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: None)
    assert classify_intent("选方案2", task="agent") == "booking"


def test_resolve_option_and_params():
    plan = _sample_plan()
    opt = resolve_option(plan, 1)
    assert opt is not None and opt["id"] == "opt-1"
    params = booking_params_from_option(
        opt,
        plan_payload={"params": {"depart_date": "2026-09-09", "return_date": "2026-09-11", "origin": "深圳", "destination": "北京"}},
    )
    assert params is not None
    assert params["flight_no"] == "ZH9101"
    assert params["return_flight_no"] == "CA1388"
    assert params["depart_date"] == "2026-09-09"
    assert params["return_date"] == "2026-09-11"


def test_persist_stores_options(session: Session):
    user = _user(session)
    plan = _sample_plan()
    record = persist_plan_record(
        session,
        user.id,
        conversation_id=None,
        params={"origin": "深圳", "destination": "北京", "depart_date": "2026-09-09", "return_date": "2026-09-11"},
        plan=plan,
        plan_html={"html": "<html></html>"},
    )
    assert record is not None
    assert len(record.payload["options"]) == 2
    assert record.payload["params"]["depart_date"] == "2026-09-09"


def test_resolve_confirm_booking_params(session: Session):
    user = _user(session)
    persist_plan_record(
        session,
        user.id,
        conversation_id=None,
        params={"origin": "深圳", "destination": "北京", "depart_date": "2026-09-09", "return_date": "2026-09-11"},
        plan=_sample_plan(),
        plan_html={},
    )
    out = resolve_confirm_booking_params(session, user.id, "确认方案1")
    assert out["ok"] is True
    assert out["params"]["flight_no"] == "ZH9101"
    assert out["params"]["return_flight_no"] == "CA1388"


def test_book_flight_pending_keeps_option_args(session: Session):
    user = _user(session)
    out = book_flight_tool(
        session,
        user.id,
        {
            "flight_no": "ZH9101",
            "depart_date": "2026-09-09",
            "return_flight_no": "CA1388",
            "return_date": "2026-09-11",
            "option_label": "ZH9101 08:00",
            "segments_summary": "去程 ZH9101（2026-09-09）；返程 CA1388（2026-09-11）",
        },
        confirmed=False,
    )
    assert out["kind"] == "pending"
    assert "ZH9101" in out["pending_action"]["summary"]
    assert out["pending_action"]["args"]["return_flight_no"] == "CA1388"


def test_book_flight_confirmed_roundtrip_two_records(session: Session):
    user = _user(session)
    out = book_flight_tool(
        session,
        user.id,
        {
            "flight_no": "ZH9101",
            "depart_date": "2026-09-09",
            "return_flight_no": "CA1388",
            "return_date": "2026-09-11",
            "origin": "深圳",
            "destination": "北京",
            "segments_summary": "去程 ZH9101；返程 CA1388",
        },
        confirmed=True,
    )
    assert out["kind"] == "booked"
    assert len(out["bookings"]) == 2
    rows = session.scalars(select(BookingRecord).where(BookingRecord.user_id == user.id)).all()
    assert len(rows) == 2
    nos = {row.payload.get("flight_no") for row in rows}
    assert nos == {"ZH9101", "CA1388"}
    assert all(row.pay_url for row in rows)


def test_booking_agent_confirm_plan_hitl(monkeypatch, session: Session):
    user = _user(session)
    persist_plan_record(
        session,
        user.id,
        conversation_id=None,
        params={"origin": "深圳", "destination": "北京", "depart_date": "2026-09-09", "return_date": "2026-09-11"},
        plan=_sample_plan(),
        plan_html={},
    )
    monkeypatch.setattr("app.booking_agent._reason_llm", lambda state: None)
    reset_booking_graph()
    out = build_booking_graph().invoke(
        booking_initial_state("确认方案1", user_id=str(user.id)),
        config={"configurable": {"session": session, "user_id": user.id}},
    )
    assert out.get("pending_action") is not None
    assert out["pending_action"]["tool"] == "book_flight"
    assert out["pending_action"]["args"]["flight_no"] == "ZH9101"
    assert "请确认" in (out.get("answer") or "")
    # 未确认前不应落库
    rows = session.scalars(select(BookingRecord).where(BookingRecord.user_id == user.id)).all()
    assert not rows
    reset_booking_graph()
