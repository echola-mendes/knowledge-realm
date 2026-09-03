"""方案页随消息落库，刷新后可回放。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db import session_scope
from app.message_ui import (
    hydrate_plan_html_from_records,
    mark_prior_hitl_resolved,
    message_to_out,
    pack_assistant_citations,
)
from app.models import Conversation, KnowledgeBase, Message, PlanRecord, User
from app.schemas import MessageOut
from app.user import ensure_default_user
from http_client import api_client


def test_pack_without_plan_keeps_list():
    assert pack_assistant_citations([{"document_id": "x"}]) == [{"document_id": "x"}]
    assert pack_assistant_citations([]) is None


def test_pack_with_plan_envelope():
    packed = pack_assistant_citations(
        [],
        plan_html={"html": "<html>ok</html>", "url": "http://x", "note": "n", "junk": 1},
    )
    assert isinstance(packed, dict)
    assert packed["citations"] == []
    assert packed["plan_html"]["html"] == "<html>ok</html>"
    assert packed["plan_html"]["url"] == "http://x"
    assert "junk" not in packed["plan_html"]


def test_message_to_out_unpacks_envelope():
    row = Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="方案已生成",
        citations={
            "citations": [{"document_id": "d1"}],
            "plan_html": {"html": "<p>a</p>", "url": None, "note": "x"},
        },
    )
    out = message_to_out(row)
    assert out.content == "方案已生成"
    assert out.citations == [{"document_id": "d1"}]
    assert out.plan_html and out.plan_html["html"] == "<p>a</p>"


@pytest.fixture
def session():
    s = session_scope()
    try:
        yield s
    finally:
        s.close()


def test_list_messages_returns_plan_html(session: Session):
    ensure_default_user(session)
    user = session.query(User).first()
    assert user is not None
    kb = KnowledgeBase(user_id=user.id, name=f"kb-{uuid.uuid4().hex[:6]}")
    session.add(kb)
    session.flush()
    convo = Conversation(user_id=user.id, knowledge_base_id=kb.id, title="t")
    session.add(convo)
    session.flush()
    session.add(Message(conversation_id=convo.id, role="user", content="去北京", citations=None))
    session.add(
        Message(
            conversation_id=convo.id,
            role="assistant",
            content="方案已生成",
            citations=pack_assistant_citations(
                [],
                plan_html={"html": "<html>plan</html>", "url": "http://example/plan", "note": "saved"},
            ),
        )
    )
    session.commit()
    cid = convo.id

    with api_client() as client:
        msgs = client.get(f"/api/conversations/{cid}/messages")
        assert msgs.status_code == 200, msgs.text
        body = msgs.json()
        assert len(body) == 2
        asst = body[1]
        assert asst["content"] == "方案已生成"
        assert asst["plan_html"]["html"] == "<html>plan</html>"
        assert asst["plan_html"]["url"] == "http://example/plan"
        assert asst["citations"] == []


def test_hydrate_attaches_plan_record_url(session: Session):
    ensure_default_user(session)
    user = session.query(User).first()
    assert user is not None
    kb = KnowledgeBase(user_id=user.id, name=f"kb-{uuid.uuid4().hex[:6]}")
    session.add(kb)
    session.flush()
    convo = Conversation(user_id=user.id, knowledge_base_id=kb.id, title="t")
    session.add(convo)
    session.flush()
    session.add(
        PlanRecord(
            user_id=user.id,
            conversation_id=convo.id,
            title="上海→北京",
            url="http://minio/plan.html",
            minio_key="plans/x.html",
        )
    )
    session.commit()
    rows = [
        MessageOut(id=uuid.uuid4(), role="user", content="q", citations=None),
        MessageOut(id=uuid.uuid4(), role="assistant", content="ok", citations=None),
    ]
    out = hydrate_plan_html_from_records(session, convo.id, rows)
    assert out[1].plan_html is not None
    assert out[1].plan_html["url"] == "http://minio/plan.html"


def test_pack_pending_and_bookings_envelope():
    packed = pack_assistant_citations(
        [],
        pending_action={"tool": "book_flight", "args": {"flight_no": "ZH9111"}, "summary": "预订ZH9111", "confirmed": None},
        bookings=[{"id": "b1", "kind": "flight", "pay_url": "https://example.com/pay/flight"}],
    )
    assert isinstance(packed, dict)
    assert packed["pending_action"]["tool"] == "book_flight"
    assert packed["bookings"][0]["id"] == "b1"


def test_message_to_out_unpacks_hitl_and_bookings():
    row = Message(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="请确认",
        citations={
            "citations": [],
            "pending_action": {"tool": "book_flight", "summary": "预订ZH9111", "confirmed": None},
        },
    )
    out = message_to_out(row)
    assert out.pending_action and out.pending_action["summary"] == "预订ZH9111"
    assert out.bookings is None


def test_mark_prior_hitl_resolved(session: Session):
    from sqlalchemy import select

    user = User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x")
    session.add(user)
    session.flush()
    kb = KnowledgeBase(user_id=user.id, name="kb")
    session.add(kb)
    session.flush()
    convo = Conversation(user_id=user.id, knowledge_base_id=kb.id, title="t", mode="agent")
    session.add(convo)
    session.flush()
    session.add(
        Message(
            conversation_id=convo.id,
            role="assistant",
            content="请确认是否预订？",
            citations={
                "citations": [],
                "pending_action": {"tool": "book_flight", "summary": "预订ZH9111", "confirmed": None},
            },
        )
    )
    session.commit()
    mark_prior_hitl_resolved(session, convo.id, confirmed=True)
    session.commit()
    row = session.scalars(select(Message).where(Message.conversation_id == convo.id)).first()
    assert row is not None
    assert row.citations["pending_action"]["confirmed"] is True
