from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage

from app.agent import graph as graph_mod
from app.agent.graph import reset_graph
from tests.http_client import api_client


def _client():
    from app.main import reset_app_state
    from app.config import get_settings

    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _sse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for part in text.split("\n\n"):
        line = next((l for l in part.split("\n") if l.startswith("data: ")), None)
        if line:
            events.append(json.loads(line[len("data: ") :]))
    return events


def _usage(total_in: int, total_out: int) -> dict[str, int]:
    return {
        "prompt_tokens": total_in,
        "completion_tokens": total_out,
        "total_tokens": total_in + total_out,
    }


def test_usage_of_and_chat_wrapper(monkeypatch):
    from app import llm as target

    class FakeResp:
        content = "答案"

        @property
        def usage_metadata(self):
            return {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

    assert target._usage_of(FakeResp()) == _usage(10, 5)
    assert target._usage_of(object()) is None
    assert target._usage_of({"input_tokens": 0}) is None

    monkeypatch.setattr(target, "chat_with_usage", lambda *a, **k: ("文本", _usage(1, 2)))
    assert target.chat("问", "资料") == "文本"


def test_trace_events_carry_tokens(monkeypatch):
    reset_graph()
    usage = _usage(100, 20)

    def fake_agent(state, config=None):
        answer = "回答"
        messages = list(state.get("messages") or [])
        messages.append({"role": "assistant", "content": answer})
        return {
            "answer": answer,
            "messages": messages,
            "agent_messages": [AIMessage(content=answer)],
            "usage": usage,
        }

    monkeypatch.setattr(graph_mod, "node_agent", fake_agent)

    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "问题", "task": "agent"})
        assert res.status_code == 200
    events = _sse_events(res.text)
    steps = [e for e in events if e["type"] == "step"]
    final = next(e for e in events if e["type"] == "final")
    agent_step = next(s for s in steps if s["node"] == "agent")
    assert agent_step["tokens"] == usage
    assert final["tokens"] == usage


def test_trace_final_tokens_zero_without_usage(monkeypatch):
    reset_graph()

    def fake_agent(state, config=None):
        answer = "直答"
        messages = list(state.get("messages") or [])
        messages.append({"role": "assistant", "content": answer})
        return {"answer": answer, "messages": messages, "agent_messages": [AIMessage(content=answer)]}

    monkeypatch.setattr(graph_mod, "node_agent", fake_agent)

    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "问题", "task": "agent"})
        assert res.status_code == 200
    final = next(e for e in _sse_events(res.text) if e["type"] == "final")
    assert final["tokens"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_node_agent_sets_answer_without_tool_calls(monkeypatch):
    reset_graph()

    class FakeModel:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return AIMessage(content="纯字符串")

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    updates = graph_mod.node_agent(
        {
            "messages": [{"role": "user", "content": "q"}],
            "agent_messages": [__import__("langchain_core.messages", fromlist=["HumanMessage"]).HumanMessage(content="q")],
            "loop_count": 0,
            "max_loops": 3,
            "tool_call_count": 0,
            "allow_web": False,
            "task": "agent",
        }
    )
    assert updates["answer"] == "纯字符串"
