from __future__ import annotations

import json

from app.agent import graph as graph_mod
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
    usage = _usage(100, 20)
    decisions = iter(
        [
            {"next_action": "generate", **{"usage": usage}},
        ]
    )
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: next(decisions))
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: ("回答", usage))

    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "问题", "task": "agent"})
        assert res.status_code == 200
    events = _sse_events(res.text)
    steps = [e for e in events if e["type"] == "step"]
    final = next(e for e in events if e["type"] == "final")
    reason_step = next(s for s in steps if s["node"] == "reason")
    generate_step = next(s for s in steps if s["node"] == "generate")
    assert reason_step["tokens"] == usage
    assert generate_step["tokens"] == usage
    assert final["tokens"] == _usage(200, 40)
    # 无 LLM 步骤（run_tool 等）不带 tokens 字段


def test_trace_final_tokens_zero_without_usage(monkeypatch):
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "直答")

    with _client() as client:
        res = client.post("/api/agent/trace", json={"query": "问题", "task": "agent"})
        assert res.status_code == 200
    final = next(e for e in _sse_events(res.text) if e["type"] == "final")
    assert final["tokens"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_node_generate_tolerates_plain_string(monkeypatch):
    monkeypatch.setattr(graph_mod, "generate_answer", lambda state: "纯字符串")
    updates = graph_mod.node_generate({"messages": [{"role": "user", "content": "q"}]})
    assert updates["answer"] == "纯字符串"
    assert "usage" not in updates
