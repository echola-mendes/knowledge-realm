import inspect
import json
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app, reset_app_state
from app.agent import graph as graph_mod
from app.agent import master as master_mod
from app.rag.search import SearchHit
import app.rag.chat as chat_mod
import app.chains as chains_mod
import app.routers.master as master_router


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    from http_client import api_client
    return api_client()


def _intent_knowledge(monkeypatch):
    monkeypatch.setattr(
        master_mod,
        "classify_intent",
        lambda query, *, task="agent", history_tail=None: "knowledge",
    )


def _sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_agent_post_uses_graph_not_chat(monkeypatch):
    src = inspect.getsource(master_router._agent_out) + inspect.getsource(master_router.agent_stream)
    assert "build_master_graph" in inspect.getsource(master_router._agent_out)
    assert "run_chat" not in src
    assert "/api/chat" not in src
    assert not inspect.iscoroutinefunction(master_router.agent_stream)
    from app.routers.chat import chat_stream
    assert not inspect.iscoroutinefunction(chat_stream)
    assert "langgraph" not in inspect.getsource(chat_mod)
    assert "langgraph" not in inspect.getsource(chains_mod)

    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    _intent_knowledge(monkeypatch)
    decisions = iter(
        [
            {"next_action": "search", "search_query": "苹果"},
            {"next_action": "generate"},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))
    searches: list[str] = []

    def fake_search(session, query, **kwargs):
        searches.append(query)
        return [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="apple.md",
                chunk_id=uuid.uuid4(),
                content="讲苹果",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "Agent假答案")

    def boom(*args, **kwargs):
        raise AssertionError("must not use chat.run_chat")

    monkeypatch.setattr("app.rag.chat.run_chat", boom)

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Agent-{uuid.uuid4().hex[:8]}"}).json()
        denied_task = client.post(
            "/api/agent",
            json={"task": "other", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert denied_task.status_code == 400
        res = client.post(
            "/api/agent",
            json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["task"] == "agent"
        assert body["knowledge_base_id"] == kb["id"]
        assert body["answer"] == "Agent假答案"
        assert body["loop_count"] == 1
        assert body["citations"][0]["document_name"] == "apple.md"
        assert searches == ["苹果"]
        assert body["conversation_id"]
        monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: False)
        denied_key = client.post(
            "/api/agent",
            json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert denied_key.status_code == 503
    reset_app_state()


def test_chat_contract_unchanged(monkeypatch):
    monkeypatch.setattr("app.ingest.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None: "假LLM答案")
    dim = get_settings().embedding_dim
    monkeypatch.setattr("app.rag.search.embed_texts", lambda texts: [[0.0] * dim for _ in texts])
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Chat-{uuid.uuid4().hex[:8]}"}).json()
        chat = client.post("/api/chat", json={"query": "你好", "knowledge_base_id": kb["id"]})
        assert chat.status_code == 200
        body = chat.json()
        assert set(body) == {"conversation_id", "answer", "citations"}
        assert body["answer"] == "假LLM答案"
        assert body["citations"] == []
    reset_app_state()


def test_agent_stream_matches_nonstream_fields(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    _intent_knowledge(monkeypatch)

    def fake_reason(state):
        if int(state.get("loop_count") or 0) == 0:
            return {"next_action": "search", "search_query": "苹果"}
        return {"next_action": "generate"}

    monkeypatch.setattr(graph_mod, "reason_decide", fake_reason)
    hit_doc = uuid.uuid4()
    hit_chunk = uuid.uuid4()

    def fake_search(session, query, **kwargs):
        return [
            SearchHit(
                document_id=hit_doc,
                document_name="apple.md",
                chunk_id=hit_chunk,
                content="讲苹果",
                score=0.9,
                page=1,
                heading=None,
                kind="note",
            )
        ]

    monkeypatch.setattr(graph_mod, "search_knowledge", fake_search)
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "Agent假答案")

    def boom(*args, **kwargs):
        raise AssertionError("must not use chat stream")

    monkeypatch.setattr("app.rag.chat.run_chat", boom)
    monkeypatch.setattr("app.routers.chat.chat_stream", boom)

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Stream-{uuid.uuid4().hex[:8]}"}).json()
        payload = {"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]}
        denied = client.post("/api/agent/stream", json={"task": "other", "query": "苹果", "knowledge_base_id": kb["id"]})
        assert denied.status_code == 400
        plain = client.post("/api/agent", json=payload)
        assert plain.status_code == 200
        streamed = client.post("/api/agent/stream", json=payload)
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(streamed.text)
        tokens = [item["text"] for item in events if item.get("type") == "token"]
        done = next(item for item in events if item.get("type") == "citations")
        assert "".join(tokens) == plain.json()["answer"]
        final = {key: value for key, value in done.items() if key != "type"}
        assert final["conversation_id"]
        assert plain.json()["conversation_id"]
        assert {k: v for k, v in final.items() if k != "conversation_id"} == {
            k: v for k, v in plain.json().items() if k != "conversation_id"
        }
        assert "document_id" in final["citations"][0]
        assert "chunk_id" in final["citations"][0]
        monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: False)
        no_key = client.post("/api/agent/stream", json=payload)
        assert no_key.status_code == 503
    reset_app_state()


def test_report_post_same_graph_as_agent(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    questions: list[str] = []

    def fake_chat(question, context, history=None, *, summary=None, ltm=None):
        questions.append(question)
        return "报告假答案"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Report-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "report", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["task"] == "report"
        assert body["answer"] == "报告假答案"
        assert "研究报告" in questions[0]
        streamed = client.post(
            "/api/agent/stream",
            json={"task": "report", "query": "苹果", "knowledge_base_id": kb["id"]},
        )
        assert streamed.status_code == 200
        done = next(item for item in _sse_events(streamed.text) if item.get("type") == "citations")
        assert done["task"] == "report"
        assert done["answer"] == "报告假答案"
    reset_app_state()


def test_agent_stm_second_turn_passes_history(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    _intent_knowledge(monkeypatch)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    seen: list[list[tuple[str, str]] | None] = []

    def fake_chat(question, context, history=None, *, summary=None, ltm=None):
        seen.append(list(history or []))
        return f"答:{question}"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"STM-{uuid.uuid4().hex[:8]}"}).json()
        first = client.post(
            "/api/agent",
            json={"task": "agent", "query": "我叫小明", "knowledge_base_id": kb["id"]},
        )
        assert first.status_code == 200
        cid = first.json()["conversation_id"]
        second = client.post(
            "/api/agent",
            json={
                "task": "agent",
                "query": "我叫什么",
                "knowledge_base_id": kb["id"],
                "conversation_id": cid,
            },
        )
        assert second.status_code == 200
        assert second.json()["conversation_id"] == cid
        assert seen[0] == []
        assert ("user", "我叫小明") in seen[1]
        assert ("assistant", "答:我叫小明") in seen[1]
        msgs = client.get(f"/api/conversations/{cid}/messages")
        assert msgs.status_code == 200
        roles = [row["role"] for row in msgs.json()]
        assert roles == ["user", "assistant", "user", "assistant"]
        assert len({cid}) == 1
    reset_app_state()


def test_agent_checkpoint_second_invoke_uses_db_stm_not_stacked(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    _intent_knowledge(monkeypatch)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    seen: list[list[tuple[str, str]]] = []

    def fake_chat(question, context, history=None, *, summary=None, ltm=None):
        seen.append(list(history or []))
        return f"答:{question}"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"CKPT-{uuid.uuid4().hex[:8]}"}).json()
        first = client.post(
            "/api/agent",
            json={"task": "agent", "query": "第一轮A", "knowledge_base_id": kb["id"]},
        )
        assert first.status_code == 200, first.text
        cid = first.json()["conversation_id"]
        config = {"configurable": {"thread_id": cid}}
        snap = graph_mod.build_graph().get_state(config)
        assert snap.values.get("messages")
        second = client.post(
            "/api/agent",
            json={
                "task": "agent",
                "query": "第二轮B",
                "knowledge_base_id": kb["id"],
                "conversation_id": cid,
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["conversation_id"] == cid
        assert seen[1] == [("user", "第一轮A"), ("assistant", "答:第一轮A")]
        assert len(seen[1]) == 2
        snap2 = graph_mod.build_graph().get_state(config)
        msgs = snap2.values.get("messages") or []
        assert msgs[-1]["role"] == "assistant"
        assert [m["content"] for m in msgs if m.get("role") == "user"] == ["第一轮A", "第二轮B"]
    reset_app_state()


def test_agent_summary_when_over_six_messages(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    _intent_knowledge(monkeypatch)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    old_secret = "远古秘密不应出现在prompt里" * 12
    summary_text = "压缩摘要：用户曾提到远古话题"

    def fake_summarize(dialogue: str) -> str:
        assert old_secret in dialogue
        return summary_text

    monkeypatch.setattr("app.rag.conversation_summary.summarize_conversation_turns", fake_summarize)
    chat_calls: list[dict] = []

    def fake_chat(question, context, history=None, *, summary=None, ltm=None):
        chat_calls.append(
            {
                "question": question,
                "history": list(history or []),
                "summary": summary,
            }
        )
        return f"答:{question}"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Sum-{uuid.uuid4().hex[:8]}"}).json()
        cid = None
        queries = [old_secret, "第二轮", "第三轮", "第四轮", "第五轮"]
        for q in queries:
            payload = {"task": "agent", "query": q, "knowledge_base_id": kb["id"]}
            if cid:
                payload["conversation_id"] = cid
            res = client.post("/api/agent", json=payload)
            assert res.status_code == 200, res.text
            cid = res.json()["conversation_id"]
        from app.db import session_scope
        from app.models import Conversation

        session = session_scope()
        try:
            convo = session.get(Conversation, uuid.UUID(cid))
            assert convo is not None
            assert convo.summary == summary_text
        finally:
            session.close()
        last = chat_calls[-1]
        assert last["summary"] == summary_text
        history_blob = " ".join(c for _, c in last["history"])
        assert old_secret not in history_blob
        assert len(last["history"]) <= 6
    reset_app_state()
