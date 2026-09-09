"""Step 4: Rewrite only INSUFFICIENT Qi; loop budget; duplicate query skip."""

from __future__ import annotations

import uuid

from app.agent import knowledge_flow as kf
from app.agent.decompose import make_sub_questions
from app.agent.graph import initial_state
from app.rag.search import SearchHit


def _complex(monkeypatch):
    monkeypatch.setattr(kf, "analyze_query", lambda query: {"query_type": "complex"})
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "ok")


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


def test_only_insufficient_qi_is_rewritten(monkeypatch):
    _complex(monkeypatch)
    questions = ["有证据", "无证据"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    rewrite_calls: list[str] = []

    def fake_rewrite(qi_question: str, *, user_query: str = ""):
        rewrite_calls.append(qi_question)
        return {"query": f"{qi_question} 改写"}

    monkeypatch.setattr(kf, "rewrite_query", fake_rewrite)

    search_calls: list[str] = []

    def fake_search(session, query, **kwargs):
        search_calls.append(query)
        if query == "有证据" or query.startswith("无证据"):
            if query == "有证据":
                return [_hit("ok")]
            if "改写" in query:
                return [_hit("filled")]
            return []
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "ok")
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("混合"),
        config={"configurable": {"session": None}},
    )
    assert rewrite_calls == ["无证据"]
    assert search_calls.count("有证据") == 1
    assert "有证据 改写" not in search_calls
    assert any(c == "无证据 改写" for c in search_calls)
    assert out["sub_questions"][0]["status"] == "SUFFICIENT"
    assert out["sub_questions"][1]["status"] == "SUFFICIENT"
    assert out["loop_count"] == 1


def test_all_sufficient_no_supplementary_retrieve(monkeypatch):
    _complex(monkeypatch)
    questions = ["A", "B"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )

    def boom_rewrite(*args, **kwargs):
        raise AssertionError("must not rewrite when all sufficient")

    monkeypatch.setattr(kf, "rewrite_query", boom_rewrite)
    search_calls: list[str] = []

    def fake_search(session, query, **kwargs):
        search_calls.append(query)
        return [_hit(query)]

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "ok")
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("都够"),
        config={"configurable": {"session": None}},
    )
    assert search_calls == ["A", "B"]
    assert out["loop_count"] == 0
    assert all(sq["status"] == "SUFFICIENT" for sq in out["sub_questions"])


def test_duplicate_query_skips_tool(monkeypatch):
    _complex(monkeypatch)
    questions = ["唯一"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    # Rewrite returns the same string → Tool must not be called again
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": qi_question},
    )
    search_calls: list[str] = []

    def fake_search(session, query, **kwargs):
        search_calls.append(query)
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    recorder = FakeRecorder()
    monkeypatch.setattr(kf, "recorder_from_config", lambda config: recorder)
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("空库"),
        config={"configurable": {"session": None}},
    )
    assert search_calls == ["唯一"]
    rewrite_spans = [
        s for s in recorder.spans if (s["decision"] or {}).get("step") == "rewrite"
    ]
    assert rewrite_spans
    assert any(
        (s["decision"] or {}).get("output", {}).get("skipped_duplicate")
        for s in rewrite_spans
    )
    assert out["sub_questions"][0]["status"] == "INSUFFICIENT"
    # rewrite_count exhausted or loops without extra tool calls
    assert out["loop_count"] == 0
    assert kf.GAP_HEADING in out["answer"]


def test_rewrite_retrieve_sufficiency_audit_spans(monkeypatch):
    _complex(monkeypatch)
    questions = ["缺口"]
    monkeypatch.setattr(
        kf,
        "decompose_query",
        lambda query: {"sub_questions": make_sub_questions(questions)},
    )
    monkeypatch.setattr(
        kf,
        "rewrite_query",
        lambda qi_question, *, user_query="": {"query": "缺口补充词"},
    )

    def fake_search(session, query, **kwargs):
        if query == "缺口补充词":
            return [_hit("now ok")]
        return []

    monkeypatch.setattr(kf, "search_knowledge", fake_search)
    monkeypatch.setattr("app.llm.chat", lambda *a, **k: "ok")
    recorder = FakeRecorder()
    monkeypatch.setattr(kf, "recorder_from_config", lambda config: recorder)
    kf.reset_knowledge_flow_graph()
    out = kf.build_knowledge_flow_graph().invoke(
        initial_state("问缺口"),
        config={"configurable": {"session": None}},
    )
    steps = [(s["decision"] or {}).get("step") for s in recorder.spans]
    assert steps[:4] == ["analyze", "decompose", "retrieve_qi", "sufficiency"]
    assert "rewrite" in steps
    # after rewrite: retrieve + sufficiency again
    rewrite_at = steps.index("rewrite")
    assert steps[rewrite_at + 1] == "retrieve_qi"
    assert steps[rewrite_at + 2] == "sufficiency"
    rw = next(s for s in recorder.spans if (s["decision"] or {}).get("step") == "rewrite")
    assert rw["decision"]["input"]["from_query"] == "缺口"
    assert rw["decision"]["output"]["to_query"] == "缺口补充词"
    assert out["loop_count"] == 1
    assert out["sub_questions"][0]["status"] == "SUFFICIENT"
