"""决策审计：task=knowledge 路径落 decision_run + analyze/retrieve/…/generate spans。"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.agent import knowledge_flow as kf
from app.agent import master as master_mod
from app.config import get_settings
from app.db import session_scope
from app.main import reset_app_state
from app.models import Conversation, DecisionRun, DecisionSpan
from app.rag.search import SearchHit


def _client():
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client

    return api_client()


def _sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _stub_knowledge_flow(monkeypatch, chunk_id: uuid.UUID):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)

    def boom_master(*args, **kwargs):
        raise AssertionError("task=knowledge must not call Master")

    monkeypatch.setattr(master_mod, "build_master_graph", boom_master)
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "simple"})
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )

    def fake_search(session, query, **kwargs):
        return [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="apple.md",
                chunk_id=chunk_id,
                content="讲苹果",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "知识Agent答案")
    kf.reset_knowledge_flow_graph()


def test_knowledge_agent_creates_decision_run_with_ordered_spans(monkeypatch):
    chunk_id = uuid.uuid4()
    _stub_knowledge_flow(monkeypatch, chunk_id)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"KB-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "knowledge", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        convo_id = uuid.UUID(res.json()["conversation_id"])

        with session_scope() as session:
            convo = session.get(Conversation, convo_id)
            assert convo is not None
            run = session.scalar(select(DecisionRun).where(DecisionRun.conversation_id == convo_id))
            assert run is not None
            assert run.mode == "knowledge"
            assert run.status == "success"
            assert run.message_id is not None
            assert run.query == "苹果"
            spans = session.scalars(
                select(DecisionSpan).where(DecisionSpan.run_id == run.id).order_by(DecisionSpan.seq)
            ).all()
            steps = [(s.node_type, (s.decision or {}).get("step")) for s in spans]
            assert steps == [
                ("route", "analyze"),
                ("retrieve", "retrieve_qi"),
                ("route", "sufficiency"),
                ("route", "merge"),
                ("route", "gap"),
                ("generate", "generate"),
            ]
            assert all(spans[i].seq < spans[i + 1].seq for i in range(len(spans) - 1))
            assert spans[0].decision["output"]["query_type"] == "simple"
            assert spans[1].evidence_refs[0]["chunk_id"] == str(chunk_id)
            assert "知识Agent答案" in spans[-1].decision["output"]["answer"]


def test_knowledge_agent_stream_also_audits(monkeypatch):
    chunk_id = uuid.uuid4()
    _stub_knowledge_flow(monkeypatch, chunk_id)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"KB-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent/stream",
            json={"task": "knowledge", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        final = [e for e in _sse_events(res.text) if e.get("type") == "citations"][0]
        convo_id = uuid.UUID(final["conversation_id"])
        with session_scope() as session:
            run = session.scalar(select(DecisionRun).where(DecisionRun.conversation_id == convo_id))
            assert run is not None
            assert run.status == "success"
            span_count = len(
                session.scalars(select(DecisionSpan).where(DecisionSpan.run_id == run.id)).all()
            )
            assert span_count == 6
