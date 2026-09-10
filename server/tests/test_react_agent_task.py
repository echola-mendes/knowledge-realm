"""task=react 直连 graph.py，不经 Master / knowledge_flow。"""
from __future__ import annotations

import json
import uuid

from app.agent import master as master_mod
from app.config import get_settings
from app.main import reset_app_state


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


def test_react_task_uses_graph_not_master(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)

    def boom_master(*args, **kwargs):
        raise AssertionError("task=react must not call Master")

    monkeypatch.setattr(master_mod, "build_master_graph", boom_master)
    monkeypatch.setattr("app.routers.master.build_master_graph", boom_master)

    called = {"graph": 0}

    class FakeReactGraph:
        def invoke(self, state, config=None):
            called["graph"] += 1
            return {
                **state,
                "answer": "ReAct答案",
                "citations": [],
                "loop_count": 1,
                "intent": "react",
            }

        def stream(self, state, config=None, stream_mode=None):
            called["graph"] += 1
            yield {
                "agent": {
                    **state,
                    "answer": "ReAct答案",
                    "citations": [],
                    "loop_count": 1,
                }
            }

    monkeypatch.setattr("app.routers.master.build_graph", lambda: FakeReactGraph())

    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"R-{uuid.uuid4().hex[:8]}"}).json()
        res = client.post(
            "/api/agent",
            json={"task": "react", "query": "查一下资料", "knowledge_base_id": kb["id"]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["task"] == "react"
        assert body["intent"] == "react"
        assert body["answer"] == "ReAct答案"
        assert called["graph"] == 1

        streamed = client.post(
            "/api/agent/stream",
            json={"task": "react", "query": "再查一次", "knowledge_base_id": kb["id"]},
        )
        assert streamed.status_code == 200
        events = _sse_events(streamed.text)
        assert events[0] == {"type": "intent", "intent": "react"}
        assert any(e.get("type") == "citations" and e.get("task") == "react" for e in events)
        assert called["graph"] == 2
    reset_app_state()
