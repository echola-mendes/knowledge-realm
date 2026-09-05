from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import KnowledgeBase, RagEvalCase, User
from app.passwords import hash_password
from app.rag.search import normalize_query
from tests.http_client import TEST_PASSWORD, api_client


def _client():
    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def test_eval_case_put_get_roundtrip():
    with _client() as client:
        missing = client.get("/api/retrieval-debug/eval-cases", params={"query": "退款周期是多久"})
        assert missing.status_code == 404

        put = client.put(
            "/api/retrieval-debug/eval-cases",
            json={"query": "退款周期是多久", "gt_answer": "7 个工作日"},
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["gt_answer"] == "7 个工作日"
        assert body["query_norm"] == normalize_query("退款周期是多久")
        assert body["knowledge_base_id"] is None

        got = client.get("/api/retrieval-debug/eval-cases", params={"query": "  退款周期是多久  "})
        assert got.status_code == 200
        assert got.json()["gt_answer"] == "7 个工作日"

        again = client.put(
            "/api/retrieval-debug/eval-cases",
            json={"query": "退款周期是多久", "gt_answer": "三个工作日"},
        )
        assert again.status_code == 200
        assert again.json()["gt_answer"] == "三个工作日"


def test_eval_case_isolated_by_user():
    with _client() as client:
        put = client.put(
            "/api/retrieval-debug/eval-cases",
            json={"query": "隔离查询", "gt_answer": "仅 echola 可见"},
        )
        assert put.status_code == 200, put.text

    other_id = uuid.uuid4()
    session = session_scope()
    try:
        session.add(User(id=other_id, username="othereval", password_hash=hash_password(TEST_PASSWORD)))
        session.flush()
        session.add(KnowledgeBase(user_id=other_id, name="别人的库", is_default=True))
        session.add(
            RagEvalCase(
                user_id=other_id,
                query_norm=normalize_query("隔离查询"),
                knowledge_base_id=None,
                gt_answer="别人的答案",
            )
        )
        session.commit()
    finally:
        session.close()

    with _client() as client:
        got = client.get("/api/retrieval-debug/eval-cases", params={"query": "隔离查询"})
        assert got.status_code == 200
        assert got.json()["gt_answer"] == "仅 echola 可见"

    reset_app_state()
    get_settings(load_file=True)
    with TestClient(create_app(load_file=True, ensure_default=True)) as other:
        login = other.post("/api/auth/login", json={"username": "othereval", "password": TEST_PASSWORD})
        assert login.status_code == 200, login.text
        got = other.get("/api/retrieval-debug/eval-cases", params={"query": "隔离查询"})
        assert got.status_code == 200
        assert got.json()["gt_answer"] == "别人的答案"
        echola_only = other.get("/api/retrieval-debug/eval-cases", params={"query": "退款周期是多久"})
        assert echola_only.status_code == 404
