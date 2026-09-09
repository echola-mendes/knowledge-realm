"""Step 7: Complex span chain (AC-10) + DecisionAuditView path check; chat AC-09 via suite."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.agent import knowledge_flow as kf
from app.agent.decompose import make_sub_questions
from app.agent.graph import initial_state
from app.rag.search import SearchHit


class FakeRecorder:
    def __init__(self) -> None:
        self.spans: list[dict] = []

    def add_span(
        self,
        node_type: str,
        *,
        decision=None,
        rationale=None,
        evidence_refs=None,
        metrics=None,
    ):
        self.spans.append(
            {
                "node_type": node_type,
                "decision": decision,
                "rationale": rationale,
                "evidence_refs": evidence_refs,
                "metrics": metrics,
            }
        )
        return uuid.uuid4()


def _hit(content: str = "body") -> SearchHit:
    return SearchHit(
        document_id=uuid.uuid4(),
        document_name="doc.md",
        chunk_id=uuid.uuid4(),
        content=content,
        score=0.9,
        page=1,
        heading=None,
        kind="note",
    )


def test_complex_span_chain_locates_nodes(monkeypatch):
    """AC-10: analyze→decompose→retrieve→sufficiency→…→merge→generate（可含 rewrite/gap）。"""
    questions = ["消息模型", "缺口子问"]
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "complex"})
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    n = 0

    def fake_rewrite(qi_question: str, *, user_query: str = ""):
        nonlocal n
        n += 1
        return {"query": f"{qi_question}#rw{n}"}

    monkeypatch.setattr(kf, "rewrite_query", fake_rewrite)

    def fake_search(session, query, **kwargs):
        if query == "消息模型" or query.startswith("消息模型"):
            return [_hit("model ok")]
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "对比回答")
    recorder = FakeRecorder()
    monkeypatch.setattr(kf, "recorder_from_config", lambda config: recorder)
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("Kafka 消息模型与缺口？"),
        config={"configurable": {"session": None}},
    )

    steps = [(s["decision"] or {}).get("step") for s in recorder.spans]
    assert steps[0] == "analyze"
    assert steps[1] == "decompose"
    assert "retrieve_qi" in steps
    assert "sufficiency" in steps
    assert "merge" in steps
    assert "generate" in steps
    # partial evidence → gap present
    assert "gap" in steps
    assert "rewrite" in steps

    def first(step: str):
        return next(s for s in recorder.spans if (s["decision"] or {}).get("step") == step)

    retrieve = first("retrieve_qi")
    assert "qi_id" in retrieve["decision"]["input"]
    assert "hit_count" in retrieve["decision"]["output"]
    assert retrieve["evidence_refs"] is not None

    suf = first("sufficiency")
    assert suf["decision"]["output"]["status"] in ("SUFFICIENT", "INSUFFICIENT")
    assert "hit_count" in suf["decision"]["output"]

    merge = first("merge")
    assert "count" in merge["decision"]["input"]
    assert "count" in merge["decision"]["output"]
    assert "ids" in merge["decision"]["output"]

    gen = first("generate")
    assert "evidence_ids" in gen["decision"]["input"]
    assert "answer" in gen["decision"]["output"]
    assert "对比回答" in out["answer"]
    assert kf.GAP_HEADING in out["answer"]


def test_decision_audit_view_exposes_step_and_io():
    """组件抽检：详情页能展示 step，并分区 input/output。"""
    vue = Path(__file__).resolve().parents[2] / "web" / "src" / "views" / "DecisionAuditView.vue"
    text = vue.read_text(encoding="utf-8")
    assert "decisionStep" in text
    assert "hasIoDecision" in text
    assert "step-pill" in text
    assert "<h4>输入</h4>" in text
    assert "<h4>输出</h4>" in text
    for step in (
        "analyze",
        "decompose",
        "retrieve_qi",
        "sufficiency",
        "rewrite",
        "merge",
        "gap",
        "generate",
    ):
        assert step in text


def test_chat_path_audit_unchanged_ac09(monkeypatch):
    """AC-09：/api/chat 不走 knowledge_flow；审计仍为 retrieve+generate（无 step）。"""
    import inspect

    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import session_scope
    from app.main import reset_app_state
    from app.models import DecisionRun, DecisionSpan
    from app.routers import chat as chat_router

    src = inspect.getsource(chat_router)
    assert "knowledge_flow" not in src
    assert "langgraph" not in src

    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "假LLM答案")
    dim = get_settings().embedding_dim
    monkeypatch.setattr(
        "app.rag.search.embed_texts",
        lambda texts: [[0.0] * dim for _ in texts],
    )

    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client

    with api_client() as client:
        resp = client.post("/api/chat", json={"query": "什么是知域"})
        assert resp.status_code == 200, resp.text
        convo_id = uuid.UUID(resp.json()["conversation_id"])

    with session_scope() as session:
        run = session.scalar(select(DecisionRun).where(DecisionRun.conversation_id == convo_id))
        assert run is not None
        assert run.mode == "chat"
        spans = session.scalars(
            select(DecisionSpan).where(DecisionSpan.run_id == run.id).order_by(DecisionSpan.seq)
        ).all()
        assert [s.node_type for s in spans] == ["retrieve", "generate"]
        assert spans[0].decision.get("tool") == "search_knowledge"
        assert "step" not in (spans[0].decision or {})
    reset_app_state()
