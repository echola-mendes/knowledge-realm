"""决策审计 API 契约：401 / 404 隔离 / 列表过滤分页 / 详情 / message 反查。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Conversation, DecisionRun, DecisionSpan, KnowledgeBase, Message, User
from app.kb import ensure_default_knowledge_base
from app.user import ensure_default_user


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def _seed_run(mode: str = "chat", status: str = "success") -> tuple[uuid.UUID, uuid.UUID]:
    """为默认用户造一条 run + spans，返回 (run_id, message_id)。"""
    with session_scope() as session:
        user = ensure_default_user(session)
        kb = ensure_default_knowledge_base(session, user.id)
        convo = Conversation(user_id=user.id, knowledge_base_id=kb.id, title="t", mode=mode)
        session.add(convo)
        session.flush()
        msg = Message(conversation_id=convo.id, role="assistant", content="答")
        session.add(msg)
        session.flush()
        run = DecisionRun(
            message_id=msg.id,
            conversation_id=convo.id,
            user_id=user.id,
            mode=mode,
            query="测试问题",
            status=status,
        )
        session.add(run)
        session.flush()
        for seq, node_type in enumerate(("route", "retrieve", "generate"), start=1):
            session.add(
                DecisionSpan(
                    run_id=run.id,
                    seq=seq,
                    node_type=node_type,
                    decision={"action": "search"} if node_type == "route" else {"summary": "答"},
                    rationale="理由",
                    evidence_refs=[{"type": "chunk", "id": f"c{seq}"}] if node_type == "retrieve" else None,
                )
            )
        session.commit()
        return run.id, msg.id


def test_decision_api_contract():
    run_id, msg_id = _seed_run()
    with _client() as client:
        # 详情：run + 有序 spans
        detail = client.get(f"/api/decisions/{run_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == str(run_id)
        assert body["message_id"] == str(msg_id)
        assert [s["seq"] for s in body["spans"]] == [1, 2, 3]
        assert body["spans"][1]["evidence_refs"][0]["id"] == "c2"

        # 列表：过滤 + 分页
        listed = client.get("/api/decisions", params={"mode": "chat", "status": "success"})
        assert listed.status_code == 200
        assert any(row["id"] == str(run_id) for row in listed.json())
        empty = client.get("/api/decisions", params={"mode": "knowledge"})
        assert all(row["id"] != str(run_id) for row in empty.json())
        paged = client.get("/api/decisions", params={"limit": 1, "offset": 0, "status": "success"})
        assert len(paged.json()) == 1
        assert paged.json()[0]["id"] == str(run_id)

        # message 反查
        via_msg = client.get(f"/api/messages/{msg_id}/decision")
        assert via_msg.status_code == 200
        assert via_msg.json()["id"] == str(run_id)

        # 不存在的资源
        assert client.get(f"/api/decisions/{uuid.uuid4()}").status_code == 404
        assert client.get(f"/api/messages/{uuid.uuid4()}/decision").status_code == 404


def test_decision_api_isolated_between_users():
    run_id, msg_id = _seed_run()
    app = create_app(load_file=True, ensure_default=False)
    other = TestClient(app)
    uname = f"other-{uuid.uuid4().hex[:6]}"
    with session_scope() as session:
        from app.passwords import hash_password

        session.add(User(username=uname, password_hash=hash_password("other-password-123")))
        session.commit()
    assert other.post("/api/auth/login", json={"username": uname, "password": "other-password-123"}).status_code == 200
    assert other.get(f"/api/decisions/{run_id}").status_code == 404
    assert other.get(f"/api/messages/{msg_id}/decision").status_code == 404
    assert other.get("/api/decisions").json() == []


def test_decision_api_requires_login():
    reset_app_state()
    get_settings(load_file=True)
    app = create_app(load_file=True, ensure_default=False)
    anon = TestClient(app)
    assert anon.get("/api/decisions").status_code == 401
