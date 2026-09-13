"""Step 1: ReactState fields + initial_state one-shot decompose."""

from __future__ import annotations

import inspect

from app.agent import graph as graph_mod
from app.agent.decompose import make_sub_questions
from app.agent.graph import build_graph, initial_state, reset_graph
from app.agent.state import ReactState


def test_react_state_has_qi_fields_not_dag_schedulers():
    hints = getattr(ReactState, "__annotations__", {})
    for key in (
        "query_type",
        "sub_questions",
        "evidence",
        "knowledge_gaps",
        "searched_queries",
    ):
        assert key in hints
    for banned in ("current_qi_index", "retrieve_phase", "next_flow"):
        assert banned not in hints


def test_build_graph_nodes_only_agent_tools():
    reset_graph()
    compiled = build_graph()
    nodes = set(compiled.get_graph().nodes)
    # LangGraph may include START/END aliases; core business nodes must be only these.
    business = {n for n in nodes if n not in {"__start__", "__end__", "START", "END"}}
    assert business == {"agent", "tools"}
    src = inspect.getsource(graph_mod.build_graph)
    assert 'add_node("decompose"' not in src
    assert 'add_node("rewrite"' not in src
    assert 'add_node("sufficiency"' not in src


def test_initial_state_simple_single_qi(monkeypatch):
    monkeypatch.setattr(
        "app.agent.analyze.analyze_query",
        lambda q: {"query_type": "simple"},
    )

    def _boom(_q: str):
        raise AssertionError("decompose must not run for simple")

    monkeypatch.setattr("app.agent.decompose.decompose_query", _boom)

    state = initial_state("苹果是什么")
    assert state["query_type"] == "simple"
    assert len(state["sub_questions"]) == 1
    qi = state["sub_questions"][0]
    assert qi["question"] == "苹果是什么"
    assert qi["id"]
    assert qi["status"] == "pending"
    assert qi["rewrite_count"] == 0
    assert qi["evidence_ids"] == []
    assert qi.get("aspects") == []
    assert qi.get("sufficiency") is None
    assert state["evidence"] == []
    assert state["knowledge_gaps"] == []
    assert state["searched_queries"] == []


def test_initial_state_complex_multi_qi(monkeypatch):
    monkeypatch.setattr(
        "app.agent.analyze.analyze_query",
        lambda q: {"query_type": "complex"},
    )
    monkeypatch.setattr(
        "app.agent.decompose.decompose_query",
        lambda q: {
            "sub_questions": make_sub_questions(
                [
                    "Kafka Rebalance 时消费停止的原因是什么？",
                    "Kafka Rebalance 导致停消费时如何排查？",
                ]
            )
        },
    )

    q = "Kafka Rebalance 时为什么消费会停？怎么排查？"
    state = initial_state(q)
    assert state["query_type"] == "complex"
    assert len(state["sub_questions"]) >= 2
    ids = [sq["id"] for sq in state["sub_questions"]]
    assert len(ids) == len(set(ids))
    for sq in state["sub_questions"]:
        assert sq["question"]
        assert "status" in sq
        assert "rewrite_count" in sq
        assert "evidence_ids" in sq


def test_initial_state_complex_degraded_to_single(monkeypatch):
    monkeypatch.setattr(
        "app.agent.analyze.analyze_query",
        lambda q: {"query_type": "complex"},
    )
    monkeypatch.setattr(
        "app.agent.decompose.decompose_query",
        lambda q: {"sub_questions": [], "degraded": True},
    )
    state = initial_state("复杂但分解失败")
    assert state["query_type"] == "simple"
    assert len(state["sub_questions"]) == 1
    assert state["sub_questions"][0]["question"] == "复杂但分解失败"
