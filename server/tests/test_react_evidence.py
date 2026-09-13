"""ReAct tool-round evidence + sufficiency post-process."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.decompose import make_sub_questions
from app.agent.evidence_sufficiency import EvidenceSufficiencyResult
from app.agent.graph import _system_prompt, initial_state
from app.agent.react_evidence import process_react_tool_round
from app.agent.sufficiency import HAS_VALID_EVIDENCE, NO_VALID_EVIDENCE


def test_process_no_hits_skips_llm_and_marks_insufficient():
    called = {"n": 0}

    def boom(_msgs):
        called["n"] += 1
        raise AssertionError("no llm")

    state = {
        "sub_questions": make_sub_questions(["原因是什么", "怎么排查"]),
        "evidence": [],
        "searched_queries": [],
        "knowledge_gaps": [],
    }
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "search_knowledge", "args": {"query": "原因是什么"}, "id": "c1"}],
    )
    tm = ToolMessage(
        content=json.dumps({"text": "未找到", "citations": []}, ensure_ascii=False),
        tool_call_id="c1",
        name="search_knowledge",
    )
    out = process_react_tool_round(
        state,
        [tm],
        ai_message=ai,
        user_question="Kafka 问题",
        llm_invoke=boom,
    )
    assert called["n"] == 0
    assert out["sufficiency"]["llm_called"] is False
    assert out["sufficiency"]["precheck"] == NO_VALID_EVIDENCE
    assert out["sufficiency"]["sufficient"] is False
    assert out["knowledge_gaps"]
    payload = json.loads(out["agent_messages"][0].content)
    assert "sufficiency" in payload
    assert "sufficiency_text" in payload
    assert "[Evidence Sufficiency]" in payload["sufficiency_text"]


def test_process_valid_hits_calls_llm_and_assigns_qi():
    def fake(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=False,
            covered_aspects=["原因"],
            missing_aspects=["排查"],
            gaps=["缺排查步骤"],
            reason="partial",
        )

    state = {
        "sub_questions": make_sub_questions(["原因是什么", "怎么排查"]),
        "evidence": [],
        "searched_queries": [],
        "knowledge_gaps": [],
    }
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "search_knowledge", "args": {"query": "原因是什么"}, "id": "c1"}],
    )
    tm = ToolMessage(
        content=json.dumps(
            {
                "text": "hit",
                "citations": [
                    {
                        "document_id": "d1",
                        "document_name": "doc",
                        "chunk_id": "ck1",
                        "content": "rebalance 会导致消费暂停",
                        "score": 0.9,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        tool_call_id="c1",
        name="search_knowledge",
    )
    out = process_react_tool_round(
        state,
        [tm],
        ai_message=ai,
        user_question="Kafka Rebalance",
        llm_invoke=fake,
    )
    assert out["sufficiency"]["llm_called"] is True
    assert out["sufficiency"]["precheck"] == HAS_VALID_EVIDENCE
    assert out["sufficiency"]["qi_id"] == "q1"
    assert any(e.get("qi_id") == "q1" for e in out["evidence"])
    q1 = next(sq for sq in out["sub_questions"] if sq["id"] == "q1")
    assert "ck1" in q1["evidence_ids"]
    assert q1["sufficiency"]["sufficient"] is False
    assert "缺排查步骤" in out["knowledge_gaps"] or any(
        "排查" in g for g in out["knowledge_gaps"]
    )
    assert "原因是什么" in out["searched_queries"]


def test_unassigned_when_query_does_not_match():
    def fake(_msgs):
        return EvidenceSufficiencyResult(sufficient=True, reason="ok")

    state = {
        "sub_questions": make_sub_questions(["原因是什么", "怎么排查"]),
        "evidence": [],
        "searched_queries": [],
    }
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "search_knowledge", "args": {"query": "完全无关词"}, "id": "c1"}],
    )
    tm = ToolMessage(
        content=json.dumps(
            {
                "citations": [
                    {
                        "document_id": "d1",
                        "document_name": "doc",
                        "chunk_id": "ck2",
                        "content": "something",
                        "score": 0.5,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        tool_call_id="c1",
        name="search_knowledge",
    )
    out = process_react_tool_round(
        state, [tm], ai_message=ai, user_question="q", llm_invoke=fake
    )
    assert out["evidence"][0]["qi_id"] == "unassigned"


def test_initial_state_resets_retrieval_fields(monkeypatch):
    monkeypatch.setattr(
        "app.agent.analyze.analyze_query",
        lambda q: {"query_type": "simple"},
    )
    s1 = initial_state("第一问")
    s1_like = {
        **s1,
        "evidence": [{"id": "old"}],
        "searched_queries": ["old-q"],
        "knowledge_gaps": ["old-gap"],
        "sufficiency": {"sufficient": True},
    }
    _ = s1_like
    s2 = initial_state("第二问", history=[{"role": "user", "content": "第一问"}, {"role": "assistant", "content": "旧答"}])
    assert s2["evidence"] == []
    assert s2["searched_queries"] == []
    assert s2["knowledge_gaps"] == []
    assert s2.get("sufficiency") == {}
    # history text only — no tool messages
    assert all(m.type in ("human", "ai") for m in s2["agent_messages"])


def test_system_prompt_includes_sufficiency_guidance():
    text = _system_prompt(
        {
            "task": "agent",
            "allow_web": False,
            "sub_questions": make_sub_questions(["a"]),
            "knowledge_gaps": ["缺配置"],
            "searched_queries": ["旧查询"],
            "sufficiency": {
                "sufficient": False,
                "precheck": "HAS_VALID_EVIDENCE",
                "qi_id": "q1",
                "missing_aspects": ["排查"],
                "rewrite_count": 1,
                "rewrite_remaining": 1,
            },
        }
    )
    assert "Evidence Sufficiency" in text or "Sufficiency" in text
    assert "knowledge_gaps" in text
    assert "禁止伪装" in text or "伪装" in text
    assert "历史" in text
    assert "searched_queries" in text or "已检索" in text
    assert "禁止精确重复" in text
    assert "missing_aspects" in text
    assert "rewrite_remaining" in text or "rewrite=" in text


def test_observation_exposes_rewrite_budget_and_searched():
    def fake(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=False,
            covered_aspects=["原因"],
            missing_aspects=["排查"],
            gaps=["缺排查步骤"],
            reason="partial",
        )

    qs = make_sub_questions(["原因是什么", "怎么排查"])
    qs[0]["evidence_ids"] = ["prior"]
    qs[0]["rewrite_count"] = 0
    state = {
        "sub_questions": qs,
        "evidence": [],
        "searched_queries": ["原因是什么"],
        "knowledge_gaps": [],
    }
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_knowledge",
                "args": {"query": "Kafka 心跳排查"},
                "id": "c1",
            }
        ],
    )
    tm = ToolMessage(
        content=json.dumps(
            {
                "citations": [
                    {
                        "document_id": "d1",
                        "document_name": "doc",
                        "chunk_id": "ck1",
                        "content": "需要看心跳",
                        "score": 0.9,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        tool_call_id="c1",
        name="search_knowledge",
    )
    out = process_react_tool_round(
        state, [tm], ai_message=ai, user_question="Kafka", llm_invoke=fake
    )
    payload = json.loads(out["agent_messages"][0].content)
    suf = payload["sufficiency"]
    assert "rewrite_count" in suf
    assert "rewrite_remaining" in suf
    assert suf["rewrite_remaining"] == max(0, 2 - int(suf["rewrite_count"]))
    assert "searched_queries" in suf
    assert "原因是什么" in suf["searched_queries"]
    obs = payload["sufficiency_text"]
    assert "rewrite_count:" in obs
    assert "rewrite_remaining:" in obs
    assert "searched_queries:" in obs
    assert "禁止精确重复" in obs or "missing_aspects" in obs


def test_observation_rewrite_exhausted_stops_encouraging_rewrite():
    from app.agent.rewrite import MAX_REWRITE_PER_Q

    def fake(_msgs):
        return EvidenceSufficiencyResult(
            sufficient=False,
            missing_aspects=["指标"],
            gaps=["仍缺指标"],
            reason="still short",
        )

    qs = make_sub_questions(["原因是什么"])
    qs[0]["evidence_ids"] = ["prior"]
    qs[0]["rewrite_count"] = MAX_REWRITE_PER_Q
    state = {
        "sub_questions": qs,
        "evidence": [],
        "searched_queries": ["原因是什么", "改写1", "改写2"],
        "knowledge_gaps": [],
    }
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_knowledge",
                "args": {"query": "又一次改写"},
                "id": "c1",
            }
        ],
    )
    tm = ToolMessage(
        content=json.dumps(
            {
                "citations": [
                    {
                        "document_id": "d1",
                        "document_name": "doc",
                        "chunk_id": "ck9",
                        "content": "x",
                        "score": 0.8,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        tool_call_id="c1",
        name="search_knowledge",
    )
    out = process_react_tool_round(
        state, [tm], ai_message=ai, user_question="Kafka", llm_invoke=fake
    )
    assert any("rewrite budget exhausted" in g for g in out["knowledge_gaps"])
    obs = json.loads(out["agent_messages"][0].content)["sufficiency_text"]
    assert "额度已用尽" in obs or "勿再盲目" in obs
    assert out["sufficiency"]["rewrite_remaining"] == 0
