"""ReAct V1 §7 Kafka 锚点：Qi / Evidence / Sufficiency / 补搜与预算（mock）。"""

from __future__ import annotations

import inspect
import json
import uuid

from langchain_core.messages import AIMessage, ToolMessage

from app.agent import graph as graph_mod
from app.agent.decompose import make_sub_questions
from app.agent.evidence_sufficiency import EvidenceSufficiencyResult
from app.agent.graph import _system_prompt, build_graph, initial_state, reset_graph
from app.agent.react_evidence import process_react_tool_round
from app.agent.sufficiency import NO_VALID_EVIDENCE

KAFKA_Q = "Kafka Rebalance 时为什么消费会停？怎么排查？"
QI_CAUSE = "Kafka Rebalance 时消费停止的原因是什么？"
QI_DEBUG = "Kafka Rebalance 导致停消费时如何排查？"
GAP_KEYWORDS = ("排查", "心跳")


def _config(thread: str):
    return {
        "configurable": {
            "thread_id": thread,
            "session": object(),
            "user_id": uuid.uuid4(),
        }
    }


def _mock_complex_kafka(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.analyze.analyze_query",
        lambda q: {"query_type": "complex"},
    )
    monkeypatch.setattr(
        "app.agent.decompose.decompose_query",
        lambda q: {
            "sub_questions": make_sub_questions([QI_CAUSE, QI_DEBUG]),
        },
    )


def _citation_tm(*, tool_call_id: str, chunk_id: str, content: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "text": "hit",
                "citations": [
                    {
                        "document_id": "d1",
                        "document_name": "kafka.md",
                        "chunk_id": chunk_id,
                        "content": content,
                        "score": 0.9,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        tool_call_id=tool_call_id,
        name="search_knowledge",
    )


def _gap_blob(*parts: object) -> str:
    bits: list[str] = []
    for p in parts:
        if isinstance(p, (list, tuple)):
            bits.extend(str(x) for x in p)
        elif p:
            bits.append(str(p))
    return " ".join(bits)


def test_kafka_anchor_init_at_least_two_qi(monkeypatch):
    _mock_complex_kafka(monkeypatch)
    state = initial_state(KAFKA_Q)
    assert state["query_type"] == "complex"
    assert len(state["sub_questions"]) >= 2
    ids = [sq["id"] for sq in state["sub_questions"]]
    assert len(ids) == len(set(ids))
    texts = " ".join(sq["question"] for sq in state["sub_questions"])
    assert "原因" in texts or "Rebalance" in texts
    assert "排查" in texts


def test_kafka_anchor_evidence_qi_and_insufficient_observation(monkeypatch):
    _mock_complex_kafka(monkeypatch)
    state = initial_state(KAFKA_Q)

    def fake(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=False,
            covered_aspects=["原因"],
            missing_aspects=["排查步骤", "心跳"],
            gaps=["缺排查步骤", "缺消费者心跳说明"],
            reason="partial coverage",
        )

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_knowledge",
                "args": {"query": QI_CAUSE},
                "id": "c1",
            }
        ],
    )
    tm = _citation_tm(
        tool_call_id="c1",
        chunk_id="ck-rebalance",
        content="Rebalance 期间分区收回，消费会暂停直到分配完成",
    )

    out = process_react_tool_round(
        state,
        [tm],
        ai_message=ai,
        user_question=KAFKA_Q,
        llm_invoke=fake,
    )

    assert any(e.get("qi_id") == "q1" for e in out["evidence"])
    assert out["sufficiency"]["llm_called"] is True
    assert out["sufficiency"]["sufficient"] is False
    missing = list(out["sufficiency"].get("missing_aspects") or [])
    gaps = list(out["sufficiency"].get("gaps") or [])
    assert missing
    assert gaps
    assert out["knowledge_gaps"]

    payload = json.loads(out["agent_messages"][0].content)
    assert "sufficiency" in payload
    assert "sufficiency_text" in payload
    obs = payload["sufficiency_text"]
    assert "[Evidence Sufficiency]" in obs or "Sufficiency" in obs
    assert payload["sufficiency"].get("missing_aspects") or payload["sufficiency"].get("gaps")


def test_kafka_anchor_no_valid_hits_skips_sufficiency_llm(monkeypatch):
    _mock_complex_kafka(monkeypatch)
    state = initial_state(KAFKA_Q)
    called = {"n": 0}

    def boom(_msgs):
        called["n"] += 1
        raise AssertionError("sufficiency LLM must not run without valid evidence")

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_knowledge",
                "args": {"query": QI_CAUSE},
                "id": "c0",
            }
        ],
    )
    tm = ToolMessage(
        content=json.dumps({"text": "未找到", "citations": []}, ensure_ascii=False),
        tool_call_id="c0",
        name="search_knowledge",
    )
    out = process_react_tool_round(
        state,
        [tm],
        ai_message=ai,
        user_question=KAFKA_Q,
        llm_invoke=boom,
    )
    assert called["n"] == 0
    assert out["sufficiency"]["llm_called"] is False
    assert out["sufficiency"]["precheck"] == NO_VALID_EVIDENCE
    assert out["sufficiency"]["sufficient"] is False


def test_kafka_anchor_graph_topology_agent_tools_only():
    reset_graph()
    compiled = build_graph()
    nodes = set(compiled.get_graph().nodes)
    business = {n for n in nodes if n not in {"__start__", "__end__", "START", "END"}}
    assert business == {"agent", "tools"}
    src = inspect.getsource(graph_mod.build_graph)
    assert 'add_node("decompose"' not in src
    assert 'add_node("rewrite"' not in src
    assert 'add_node("sufficiency"' not in src


def test_kafka_followup_query_targets_gaps_not_repeat(monkeypatch):
    """首轮不足 → 次轮注入的 tool query 须与 gaps/missing 相关，且非首轮同义重复。"""
    _mock_complex_kafka(monkeypatch)
    state = initial_state(KAFKA_Q)
    round1_query = QI_CAUSE

    def fake_r1(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=False,
            covered_aspects=["原因"],
            missing_aspects=["排查步骤", "心跳"],
            gaps=["缺排查步骤", "缺消费者心跳说明"],
            reason="partial",
        )

    ai1 = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_knowledge", "args": {"query": round1_query}, "id": "r1"}
        ],
    )
    out1 = process_react_tool_round(
        state,
        [
            _citation_tm(
                tool_call_id="r1",
                chunk_id="ck1",
                content="Rebalance 会暂停消费",
            )
        ],
        ai_message=ai1,
        user_question=KAFKA_Q,
        llm_invoke=fake_r1,
    )
    gap_text = _gap_blob(
        out1["sufficiency"].get("missing_aspects"),
        out1["sufficiency"].get("gaps"),
        out1.get("knowledge_gaps"),
    )
    assert any(k in gap_text for k in GAP_KEYWORDS)

    # Agent 按 Observation 补搜（mock 注入）：对准缺口词，非首轮 query 重复。
    round2_query = "Kafka 消费者心跳超时如何排查"
    assert round2_query != round1_query
    assert round2_query.strip() != round1_query.strip()
    assert any(k in round2_query for k in GAP_KEYWORDS if k in gap_text)

    def fake_r2(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=True,
            covered_aspects=["原因", "排查步骤", "心跳"],
            missing_aspects=[],
            gaps=[],
            reason="ok",
        )

    state2 = {**state, **{k: out1[k] for k in (
        "evidence",
        "sub_questions",
        "knowledge_gaps",
        "searched_queries",
        "sufficiency",
    ) if k in out1}}
    ai2 = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_knowledge", "args": {"query": round2_query}, "id": "r2"}
        ],
    )
    out2 = process_react_tool_round(
        state2,
        [
            _citation_tm(
                tool_call_id="r2",
                chunk_id="ck2",
                content="检查 session.timeout 与心跳间隔",
            )
        ],
        ai_message=ai2,
        user_question=KAFKA_Q,
        llm_invoke=fake_r2,
    )
    assert round2_query in out2["searched_queries"]
    assert round1_query in out2["searched_queries"]
    assert round2_query != round1_query
    # Soft constraint: follow-up must not be an exact duplicate of already-searched queries.
    assert round2_query not in [round1_query]
    gap_tokens = {"排查", "心跳", "session"}
    assert any(t in round2_query for t in gap_tokens)
    obs2 = json.loads(out2["agent_messages"][0].content)
    assert "rewrite_count" in obs2["sufficiency"]
    assert "rewrite_remaining" in obs2["sufficiency"]
    assert "searched_queries" in obs2["sufficiency"]


def test_budget_exhausted_keeps_knowledge_gaps(monkeypatch):
    """tool 预算用尽且仍 insufficient 时，knowledge_gaps 与 prompt 仍可见。"""
    _mock_complex_kafka(monkeypatch)
    reset_graph()
    gaps = ["缺排查步骤", "缺消费者心跳说明"]

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            raise AssertionError("budget exhausted should not bind tools")

        def invoke(self, messages, config=None):
            return AIMessage(content="预算尽：仍缺排查与心跳说明")

        def stream(self, messages, config=None):
            yield self.invoke(messages, config)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())

    state = initial_state(KAFKA_Q)
    state["tool_call_count"] = graph_mod.MAX_TOOL_CALLS
    state["knowledge_gaps"] = list(gaps)
    state["sufficiency"] = {
        "sufficient": False,
        "precheck": "HAS_VALID_EVIDENCE",
        "qi_id": "q2",
        "missing_aspects": ["排查步骤", "心跳"],
        "gaps": list(gaps),
    }

    prompt = _system_prompt(state)
    assert "knowledge_gaps" in prompt
    assert gaps[0] in prompt

    out = build_graph().invoke(state, config=_config(f"gaps-budget-{uuid.uuid4()}"))
    assert out["tool_call_count"] == graph_mod.MAX_TOOL_CALLS
    assert out.get("knowledge_gaps")
    assert any(g in out["knowledge_gaps"] for g in gaps)
    assert out.get("answer")


def test_kafka_new_round_resets_retrieval_state(monkeypatch):
    """同 conversation 新一轮 initial_state 不继承上一轮检索态。"""
    _mock_complex_kafka(monkeypatch)
    s1 = initial_state(KAFKA_Q)
    polluted = {
        **s1,
        "evidence": [{"id": "old", "qi_id": "q1"}],
        "searched_queries": [QI_CAUSE],
        "knowledge_gaps": ["旧缺口"],
        "sufficiency": {"sufficient": False, "gaps": ["旧缺口"]},
    }
    _ = polluted

    s2 = initial_state(
        "补充：还有哪些排查手段？",
        history=[
            {"role": "user", "content": KAFKA_Q},
            {"role": "assistant", "content": "上次回答（含旧缺口）"},
        ],
    )
    assert s2["evidence"] == []
    assert s2["searched_queries"] == []
    assert s2["knowledge_gaps"] == []
    assert s2.get("sufficiency") == {}
    assert all(m.type in ("human", "ai") for m in s2["agent_messages"])
    assert not any(isinstance(m, ToolMessage) for m in s2["agent_messages"])
