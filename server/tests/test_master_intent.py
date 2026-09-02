import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app, reset_app_state
from app import graph as graph_mod
from app import master as master_mod
from app.intent import classify_intent
import app.intent as intent_mod
from app.master import (
    build_master_graph,
    master_initial_state,
)


def _client() -> TestClient:
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


def _master_config() -> dict:
    return {
        "configurable": {
            "thread_id": f"master-{uuid.uuid4()}",
            "session": object(),
            "user_id": uuid.uuid4(),
        }
    }


def _no_label(monkeypatch):
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: None)


def _intent_of(label: str):
    return lambda query, *, task="agent", history_tail=None: label


# ---------- 薄意图 classify_intent ----------


def test_classify_report_forces_knowledge(monkeypatch):
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "plan")
    assert classify_intent("帮我规划下周行程", task="report") == "knowledge"


def test_classify_llm_label_wins_over_heuristic(monkeypatch):
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "knowledge")
    assert classify_intent("酒店管理系统的文档有哪些", task="agent") == "knowledge"


def test_classify_heuristic_fallback(monkeypatch):
    _no_label(monkeypatch)
    assert classify_intent("帮我订机票", task="agent") == "booking"
    assert classify_intent("下周二去上海，帮我规划行程", task="agent") == "plan"
    assert classify_intent("下周二上海出发去北京，周四返回，经济舱", task="agent") == "plan"
    assert classify_intent("你好", task="agent") == "chat"
    assert classify_intent("什么是RAG", task="agent") == "knowledge"




def test_classify_oral_signal_overrides_knowledge_without_cabin(monkeypatch):
    """正向：城市+日期+返回，无舱位；LLM=knowledge → plan（PRD §4.3）。"""
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "knowledge")
    assert classify_intent("下周二去上海，周四返回", task="agent") == "plan"


def test_classify_cabin_route_corrects_knowledge(monkeypatch):
    """纠偏：舱位+路线；LLM=knowledge → plan。"""
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "knowledge")
    assert classify_intent("下周二上海出发去北京，周四返回，经济舱", task="agent") == "plan"


def test_classify_llm_booking_not_overridden_by_oral_rules(monkeypatch):
    monkeypatch.setattr(intent_mod, "_llm_label", lambda query, history_tail=None: "booking")
    assert classify_intent("下周二上海出发去北京，周四返回，经济舱", task="agent") == "booking"


# ---------- Master 图路由 ----------


def test_master_knowledge_invokes_subgraph(monkeypatch):
    calls: dict = {}

    class FakeGraph:
        def invoke(self, state, config=None):
            calls["state"] = state
            calls["config"] = config
            return {"answer": "知识答案", "citations": [{"document_name": "apple.md"}], "loop_count": 1}

    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("knowledge"))
    monkeypatch.setattr(master_mod, "build_graph", lambda: FakeGraph())
    convo_id = uuid.uuid4()
    out = build_master_graph().invoke(
        master_initial_state("苹果是什么", conversation_id=convo_id),
        config=_master_config(),
    )
    assert out["answer"] == "知识答案"
    assert out["intent"] == "knowledge"
    assert out["citations"] == [{"document_name": "apple.md"}]
    assert calls["config"]["configurable"]["thread_id"] == str(convo_id)
    assert calls["state"]["messages"][-1] == {"role": "user", "content": "苹果是什么"}


def test_master_chat_replies_without_knowledge_subgraph(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("chat 意图不应调用 knowledge 子图")

    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("chat"))
    monkeypatch.setattr(master_mod, "build_graph", boom)
    monkeypatch.setattr(
        "app.llm.chat",
        lambda question, context, history=None, *, summary=None, ltm=None: "你好呀",
    )
    out = build_master_graph().invoke(master_initial_state("你好"), config=_master_config())
    assert out["answer"] == "你好呀"
    assert out["citations"] == []


def test_master_plan_routes_to_plan_agent(monkeypatch):
    import app.plan_agent as plan_mod

    seen: dict = {}

    class FakePlanGraph:
        def invoke(self, state, config=None):
            seen["state"] = state
            seen["config"] = config
            return {
                "answer": "方案已生成",
                "progress": ["机票搜索完成（3 条）"],
                "travel_data": {"flights": [{"flightNo": "MU5101"}]},
                "plan_html": {"html": "<html></html>", "url": None, "note": "MinIO 未配置"},
            }

    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("plan"))
    monkeypatch.setattr("app.plan_agent.build_plan_graph", lambda: FakePlanGraph())
    monkeypatch.setattr(master_mod, "build_graph", lambda *a, **k: (_ for _ in ()).throw(AssertionError("plan 不应走 knowledge")))
    out = build_master_graph().invoke(
        master_initial_state("帮我规划行程", conversation_id=uuid.uuid4()),
        config=_master_config(),
    )
    assert out["answer"] == "方案已生成"
    assert out["intent"] == "plan"
    assert out["citations"] == []
    assert out["travel_data"]["flights"][0]["flightNo"] == "MU5101"
    assert seen["state"]["messages"][-1] == {"role": "user", "content": "帮我规划行程"}


def test_master_booking_routes_to_booking_agent(monkeypatch):
    import app.booking_agent as booking_mod

    seen: dict = {}

    class FakeBookingGraph:
        def invoke(self, state, config=None):
            seen["state"] = state
            return {"answer": "预订助手已收到", "pending_action": None}

    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("booking"))
    monkeypatch.setattr("app.booking_agent.build_booking_graph", lambda: FakeBookingGraph())
    out = build_master_graph().invoke(
        master_initial_state("帮我订机票"), config=_master_config()
    )
    assert out["answer"] == "预订助手已收到"
    assert out["intent"] == "booking"
    assert seen["state"]["messages"][-1] == {"role": "user", "content": "帮我订机票"}
    assert out["citations"] == []


# ---------- 路由契约 ----------


def test_agent_router_contract_knowledge(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("knowledge"))
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None, *, summary=None, ltm=None: "Router答案")
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Master-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post("/api/agent", json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]})
        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "Router答案"
        assert body["citations"] == []
        assert body["intent"] == "knowledge"
        assert body["conversation_id"]
    reset_app_state()


def test_agent_router_stream_first_event_is_intent(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("knowledge"))
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    monkeypatch.setattr("app.llm.chat", lambda question, context, history=None, *, summary=None, ltm=None: "流式答案")
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Stream-{uuid.uuid4().hex[:8]}"}).json()
        plain = client.post("/api/agent", json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]})
        assert plain.status_code == 200
        streamed = client.post("/api/agent/stream", json={"task": "agent", "query": "苹果", "knowledge_base_id": kb["id"]})
        assert streamed.status_code == 200
        events = _sse_events(streamed.text)
        assert events[0] == {"type": "intent", "intent": "knowledge"}
        tokens = [item["text"] for item in events if item.get("type") == "token"]
        done = next(item for item in events if item.get("type") == "citations")
        assert "".join(tokens) == "流式答案"
        assert done["answer"] == plain.json()["answer"]
        assert done["intent"] == "knowledge"
    reset_app_state()


def test_agent_router_plan_not_500(monkeypatch):
    class FakePlanGraph:
        def invoke(self, state, config=None):
            return {"answer": "方案假答案", "progress": [], "travel_data": {}, "plan_html": {}}

    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("plan"))
    monkeypatch.setattr("app.plan_agent.build_plan_graph", lambda: FakePlanGraph())
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Plan-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post("/api/agent", json={"task": "agent", "query": "规划上海行程", "knowledge_base_id": kb["id"]})
        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "方案假答案"
        assert body["intent"] == "plan"
        assert body["citations"] == []
    reset_app_state()


def test_agent_router_booking_not_500(monkeypatch):
    import app.booking_agent as booking_mod

    class FakeBookingGraph:
        def invoke(self, state, config=None):
            return {"answer": "预订假答案", "pending_action": None}

    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("booking"))
    monkeypatch.setattr("app.booking_agent.build_booking_graph", lambda: FakeBookingGraph())
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"Book-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post("/api/agent", json={"task": "agent", "query": "帮我订机票", "knowledge_base_id": kb["id"]})
        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == "预订假答案"
        assert body["intent"] == "booking"
        assert body["citations"] == []
    reset_app_state()


def test_agent_router_stream_plan_events(monkeypatch):
    """plan 路径 SSE：intent → progress/travel_data/plan_html → token → citations。"""

    class FakePlanGraph:
        def invoke(self, state, config=None):
            emit = (config.get("configurable") or {}).get("emit")
            if callable(emit):
                emit({"type": "progress", "text": "机票搜索完成（3 条）"})
                emit({"type": "travel_data", "flights": [{"flightNo": "MU5101"}]})
                emit({"type": "plan_html", "html": "<html>方案</html>", "url": None, "note": "MinIO 未配置"})
            return {
                "answer": "方案已生成：推荐 opt-1",
                "progress": [],
                "travel_data": {"flights": [{"flightNo": "MU5101"}]},
                "plan_html": {"html": "<html>方案</html>", "url": None, "note": "MinIO 未配置"},
            }

    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("plan"))
    monkeypatch.setattr("app.plan_agent.build_plan_graph", lambda: FakePlanGraph())
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"PlanS-{uuid.uuid4().hex[:8]}"}).json()
        streamed = client.post(
            "/api/agent/stream", json={"task": "agent", "query": "规划上海行程", "knowledge_base_id": kb["id"]}
        )
        assert streamed.status_code == 200
        events = _sse_events(streamed.text)
        types = [e["type"] for e in events]
        assert types[0] == "intent"
        assert "progress" in types and "travel_data" in types and "plan_html" in types
        assert types.index("travel_data") < types.index("plan_html") < types.index("token")
        plan_evt = next(e for e in events if e["type"] == "plan_html")
        assert plan_evt["url"] is None and "未配置" in plan_evt["note"]
        done = next(e for e in events if e["type"] == "citations")
        assert done["intent"] == "plan"
        assert done["answer"] == "方案已生成：推荐 opt-1"
    reset_app_state()


def test_agent_router_stream_booking_events(monkeypatch):
    """booking 路径 SSE：intent → hitl → token → citations（含 pending_action / bookings）。"""

    class FakeBookingGraph:
        def invoke(self, state, config=None):
            emit = (config.get("configurable") or {}).get("emit")
            pending = {
                "tool": "book_flight",
                "args": {"flight_no": "MU5101", "depart_date": "2026-09-10"},
                "summary": "预订机票 MU5101（2026-09-10）",
            }
            if callable(emit):
                emit({"type": "hitl", **pending})
            return {
                "answer": "请确认是否预订机票 MU5101（2026-09-10）？",
                "pending_action": pending,
                "bookings": [],
            }

    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(master_mod, "classify_intent", _intent_of("booking"))
    monkeypatch.setattr("app.booking_agent.build_booking_graph", lambda: FakeBookingGraph())
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"BookS-{uuid.uuid4().hex[:8]}"}).json()
        streamed = client.post(
            "/api/agent/stream",
            json={"task": "agent", "query": "订这个航班 MU5101", "knowledge_base_id": kb["id"]},
        )
        assert streamed.status_code == 200
        events = _sse_events(streamed.text)
        types = [e["type"] for e in events]
        assert types[0] == "intent"
        assert "hitl" in types
        assert types.index("hitl") < types.index("token")
        hitl_evt = next(e for e in events if e["type"] == "hitl")
        assert hitl_evt["tool"] == "book_flight"
        done = next(e for e in events if e["type"] == "citations")
        assert done["intent"] == "booking"
        assert done["pending_action"]["tool"] == "book_flight"
    reset_app_state()
