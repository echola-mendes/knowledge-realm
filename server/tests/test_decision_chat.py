import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit import DecisionRecorder
from app.config import get_settings
from app.db import session_scope
from app.main import create_app, reset_app_state
from app.models import Conversation, DecisionRun, DecisionSpan, Message


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def test_chat_creates_decision_run_with_spans(monkeypatch):
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "假LLM答案")
    with _client() as client:
        resp = client.post("/api/chat", json={"query": "什么是知域"})
        assert resp.status_code == 200, resp.text
        convo_id = uuid.UUID(resp.json()["conversation_id"])

        with session_scope() as session:
            convo = session.get(Conversation, convo_id)
            assert convo is not None
            run = session.scalar(
                select(DecisionRun).where(DecisionRun.conversation_id == convo_id)
            )
            assert run is not None
            assert run.mode == "chat"
            assert run.status == "success"
            assert run.query == "什么是知域"
            assert run.message_id is not None
            assistant = session.get(Message, run.message_id)
            assert assistant is not None and assistant.role == "assistant"
            spans = session.scalars(
                select(DecisionSpan).where(DecisionSpan.run_id == run.id).order_by(DecisionSpan.seq)
            ).all()
            assert [s.node_type for s in spans] == ["retrieve", "generate"]
            assert spans[0].decision["tool"] == "search_knowledge"


def test_stream_chat_also_audits(monkeypatch):
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "流式答案")
    with _client() as client:
        with client.stream("POST", "/api/chat/stream", json={"query": "流式问题"}) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
        assert "流式答案" in body
        convo_id = uuid.UUID(body.split('"conversation_id": "')[1].split('"')[0])
        with session_scope() as session:
            runs = session.scalars(
                select(DecisionRun).where(DecisionRun.conversation_id == convo_id)
            ).all()
            assert len(runs) == 1
            assert runs[0].status == "success"


class _BrokenRecorder(DecisionRecorder):
    """模拟审计库不可用：独立 session 建不出来，recorder 全程吞异常。"""

    def __init__(self, **kwargs):
        class BrokenFactory:
            def __call__(self):
                raise RuntimeError("audit db down")

        super().__init__(session_factory=BrokenFactory)


def test_chat_survives_recorder_failure(monkeypatch):
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "仍然能答")
    monkeypatch.setattr("app.routers.chat.DecisionRecorder", _BrokenRecorder)
    with _client() as client:
        resp = client.post("/api/chat", json={"query": "审计挂了也能答"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["answer"] == "仍然能答"
