"""
Knowledge Agent flow (Sufficiency V0):
  analyze → (simple | complex)
    simple  → 单 Qi 检索 → sufficiency → … → merge → gap → generate
    complex → decompose → per-Qi retrieve → …
  → rewrite（仅 INSUFFICIENT）→ merge → gap → generate

task=knowledge 入口走本图；Master 内旧 reason→run_tool 图仍保留给其它路径。
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent.analyze import analyze_decision, analyze_query
from app.agent.decompose import (
    MAX_SUB_QUESTIONS,
    decompose_decision,
    decompose_query,
    fallback_single_qi,
)
from app.agent.evidence_merge import (
    MAX_EVIDENCE,
    evidence_from_hit,
    merge_decision,
    merge_evidence,
    merge_evidence_refs,
)
from app.agent.graph import MAX_LOOPS, AgentState, _user_question
from app.agent.rewrite import MAX_REWRITE_PER_Q, rewrite_decision, rewrite_query
from app.agent.sufficiency import knowledge_span_decision, sufficiency_decision, sufficiency_v0
from app.agent.tools import search_knowledge
from app.audit.evidence import context_assembly_summary, search_hit_evidence_ref
from app.audit.recorder import recorder_from_config

_compiled_knowledge = None
GAP_HEADING = "## Knowledge Gap"


def _qi_hits(state: AgentState, qi: dict[str, Any]) -> list[dict[str, Any]]:
    qi_id = str(qi.get("id") or "")
    evidence_ids = set(str(x) for x in (qi.get("evidence_ids") or []))
    pool = list(state.get("evidence") or [])
    return [
        e
        for e in pool
        if str(e.get("qi_id") or "") == qi_id or str(e.get("id") or "") in evidence_ids
    ]


def _current_qi(state: AgentState) -> dict[str, Any] | None:
    qs = list(state.get("sub_questions") or [])
    idx = int(state.get("current_qi_index") or 0)
    if idx < 0 or idx >= len(qs):
        return None
    return qs[idx]


def _pick_rewrite_index(state: AgentState) -> int | None:
    if int(state.get("loop_count") or 0) >= int(state.get("max_loops") or MAX_LOOPS):
        return None
    for i, sq in enumerate(state.get("sub_questions") or []):
        if str(sq.get("status") or "") != "INSUFFICIENT":
            continue
        if int(sq.get("rewrite_count") or 0) >= MAX_REWRITE_PER_Q:
            continue
        return i
    return None


def node_analyze(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    query = _user_question(state)
    result = analyze_query(query)
    query_type = str(result.get("query_type") or "simple").strip().lower()
    if query_type not in ("simple", "complex"):
        query_type = "simple"

    recorder = recorder_from_config(config)
    if recorder:
        metrics = result.get("usage")
        recorder.add_span(
            "route",
            decision=analyze_decision(query, query_type),  # type: ignore[arg-type]
            metrics=metrics if isinstance(metrics, dict) else None,
        )

    updates: dict[str, Any] = {
        "query_type": query_type,
        "evidence": list(state.get("evidence") or []),
        "searched_queries": list(state.get("searched_queries") or []),
        "knowledge_gaps": list(state.get("knowledge_gaps") or []),
        "loop_count": int(state.get("loop_count") or 0),
        "retrieve_phase": "initial",
        "search_query": "",
        "skip_retrieve": False,
        "current_qi_index": 0,
    }
    if query_type == "simple":
        updates["sub_questions"] = fallback_single_qi(query)
        updates["next_flow"] = "retrieve_qi"
    else:
        updates["sub_questions"] = []
        updates["next_flow"] = "decompose"
    return updates


def route_after_analyze(state: AgentState) -> Literal["retrieve_qi", "decompose"]:
    if str(state.get("query_type") or "") == "complex":
        return "decompose"
    return "retrieve_qi"


def node_decompose(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    query = _user_question(state)
    result = decompose_query(query)
    sub_questions = list(result.get("sub_questions") or fallback_single_qi(query))
    if len(sub_questions) > MAX_SUB_QUESTIONS:
        sub_questions = sub_questions[:MAX_SUB_QUESTIONS]
    # Decomposition 失败/空 → 降级单 Qi（与 Simple 等价：原 query 检索一次）
    degraded = bool(result.get("degraded")) or not sub_questions
    if degraded:
        sub_questions = fallback_single_qi(query)

    recorder = recorder_from_config(config)
    if recorder:
        metrics = result.get("usage")
        recorder.add_span(
            "route",
            decision=decompose_decision(query, sub_questions),
            rationale="Decomposition 失败，降级单次检索" if degraded else None,
            metrics=metrics if isinstance(metrics, dict) else None,
        )
    return {
        "sub_questions": sub_questions,
        "current_qi_index": 0,
        "evidence": list(state.get("evidence") or []),
        "searched_queries": list(state.get("searched_queries") or []),
        "knowledge_gaps": list(state.get("knowledge_gaps") or []),
        "loop_count": int(state.get("loop_count") or 0),
        "query_type": "simple" if degraded else (state.get("query_type") or "complex"),
        "retrieve_phase": "initial",
        "search_query": "",
        "skip_retrieve": False,
        "next_flow": "",
    }


def node_retrieve_qi(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    qi = _current_qi(state)
    if qi is None:
        return {}
    session = (config.get("configurable") or {}).get("session")
    user_id = (config.get("configurable") or {}).get("user_id")
    kb_raw = state.get("knowledge_base_id")
    kb_id = uuid.UUID(kb_raw) if kb_raw else None
    qi_id = str(qi.get("id") or "")
    phase = str(state.get("retrieve_phase") or "initial")
    if phase == "rewrite" and str(state.get("search_query") or "").strip():
        query = str(state.get("search_query") or "").strip()
    else:
        query = str(qi.get("question") or "").strip()

    searched = list(state.get("searched_queries") or [])
    loop_count = int(state.get("loop_count") or 0)
    recorder = recorder_from_config(config)

    # Exact duplicate → skip Tool (AC-07)
    if query and query in searched:
        if recorder:
            recorder.add_span(
                "retrieve",
                decision=knowledge_span_decision(
                    "retrieve_qi",
                    input={"qi_id": qi_id, "query": query},
                    output={
                        "hit_count": 0,
                        "hit_ids": [],
                        "skipped_duplicate": True,
                    },
                ),
                rationale="重复 query，跳过 Tool",
            )
        return {
            "loop_count": loop_count,
            "last_qi_hits": 0,
            "skip_retrieve": True,
        }

    tool_started = time.monotonic()
    hits = search_knowledge(session, query, user_id=user_id, knowledge_base_id=kb_id)
    if phase == "rewrite":
        loop_count += 1

    evidence = list(state.get("evidence") or [])
    evidence_ids: list[str] = []
    for hit in hits:
        item = evidence_from_hit(hit, qi_id=qi_id, question=str(qi.get("question") or query))
        evidence.append(item)
        evidence_ids.append(str(item["id"]))

    sub_questions = [dict(sq) for sq in (state.get("sub_questions") or [])]
    idx = int(state.get("current_qi_index") or 0)
    if 0 <= idx < len(sub_questions):
        prev_ids = list(sub_questions[idx].get("evidence_ids") or [])
        for eid in evidence_ids:
            if eid not in prev_ids:
                prev_ids.append(eid)
        sub_questions[idx]["evidence_ids"] = prev_ids

    if query and query not in searched:
        searched.append(query)

    if recorder:
        recorder.add_span(
            "retrieve",
            decision=knowledge_span_decision(
                "retrieve_qi",
                input={"qi_id": qi_id, "query": query},
                output={
                    "hit_count": len(hits),
                    "hit_ids": [str(h.chunk_id) for h in hits],
                    "context_assembly": context_assembly_summary(hits),
                    "skipped_duplicate": False,
                },
            ),
            evidence_refs=[search_hit_evidence_ref(h, qi_id=qi_id) for h in hits],
            metrics={
                "elapsed_ms": int((time.monotonic() - tool_started) * 1000),
                "hits": len(hits),
            },
        )

    return {
        "evidence": evidence,
        "sub_questions": sub_questions,
        "searched_queries": searched,
        "loop_count": loop_count,
        "last_qi_hits": len(hits),
        "skip_retrieve": False,
    }


def node_sufficiency(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    qi = _current_qi(state)
    if qi is None:
        return {}
    qi_id = str(qi.get("id") or "")
    query = str(qi.get("question") or "")
    qi_hits = _qi_hits(state, qi)
    status = sufficiency_v0(qi_hits)

    sub_questions = [dict(sq) for sq in (state.get("sub_questions") or [])]
    idx = int(state.get("current_qi_index") or 0)
    if 0 <= idx < len(sub_questions):
        sub_questions[idx]["status"] = status

    recorder = recorder_from_config(config)
    if recorder:
        recorder.add_span(
            "route",
            decision=sufficiency_decision(qi_hits, qi_id=qi_id, query=query),
            evidence_refs=[
                {
                    "type": "chunk",
                    "id": str(e.get("id") or ""),
                    "chunk_id": str(e.get("chunk_id") or e.get("id") or ""),
                    "document_id": str(e.get("document_id") or ""),
                    "document_name": e.get("document_name"),
                    "score": e.get("score"),
                    "excerpt": str(e.get("content") or "")[:120],
                    "qi_id": qi_id,
                }
                for e in qi_hits
            ],
        )

    updates: dict[str, Any] = {
        "sub_questions": sub_questions,
        "loop_count": int(state.get("loop_count") or 0),
    }
    phase = str(state.get("retrieve_phase") or "initial")
    if phase == "initial":
        updates["current_qi_index"] = idx + 1
    return updates


def node_rewrite(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    """Pick next INSUFFICIENT Qi, rewrite query, or signal done."""
    idx = _pick_rewrite_index(state)
    if idx is None:
        return {
            "next_flow": "done",
            "retrieve_phase": "rewrite",
            "skip_retrieve": False,
            "search_query": "",
        }

    sub_questions = [dict(sq) for sq in (state.get("sub_questions") or [])]
    qi = sub_questions[idx]
    qi_id = str(qi.get("id") or "")
    from_query = str(qi.get("question") or "").strip()
    user_query = _user_question(state)
    result = rewrite_query(from_query, user_query=user_query)
    to_query = str(result.get("query") or from_query).strip() or from_query

    qi["rewrite_count"] = int(qi.get("rewrite_count") or 0) + 1
    sub_questions[idx] = qi

    searched = list(state.get("searched_queries") or [])
    skipped = bool(to_query and to_query in searched)

    recorder = recorder_from_config(config)
    if recorder:
        metrics = result.get("usage")
        recorder.add_span(
            "route",
            decision=rewrite_decision(
                qi_id=qi_id,
                from_query=from_query,
                to_query=to_query,
                skipped=skipped,
            ),
            rationale="重复 query，将跳过 Tool" if skipped else None,
            metrics=metrics if isinstance(metrics, dict) else None,
        )

    if skipped:
        # No Tool call; try another rewrite candidate next
        return {
            "sub_questions": sub_questions,
            "current_qi_index": idx,
            "search_query": to_query,
            "retrieve_phase": "rewrite",
            "skip_retrieve": True,
            "next_flow": "rewrite",
        }

    return {
        "sub_questions": sub_questions,
        "current_qi_index": idx,
        "search_query": to_query,
        "retrieve_phase": "rewrite",
        "skip_retrieve": False,
        "next_flow": "retrieve_qi",
    }


def route_after_sufficiency(state: AgentState) -> Literal["retrieve_qi", "rewrite"]:
    phase = str(state.get("retrieve_phase") or "initial")
    if phase == "initial":
        qs = list(state.get("sub_questions") or [])
        idx = int(state.get("current_qi_index") or 0)
        if idx < len(qs):
            return "retrieve_qi"
        return "rewrite"
    return "rewrite"


def route_after_rewrite(state: AgentState) -> Literal["retrieve_qi", "rewrite", "merge"]:
    nxt = str(state.get("next_flow") or "")
    if nxt == "done":
        return "merge"
    if state.get("skip_retrieve"):
        return "rewrite"
    return "retrieve_qi"


def collect_knowledge_gaps(sub_questions: list[dict[str, Any]] | None) -> list[str]:
    """Questions still INSUFFICIENT after retrieve budget → Knowledge Gap list."""
    gaps: list[str] = []
    for sq in sub_questions or []:
        if str(sq.get("status") or "") != "INSUFFICIENT":
            continue
        text = str(sq.get("question") or "").strip()
        if text and text not in gaps:
            gaps.append(text)
    return gaps


def gap_decision(
    insufficient_qi: list[dict[str, Any]],
    gaps: list[str],
) -> dict[str, Any]:
    return knowledge_span_decision(
        "gap",
        input={"insufficient_qi": insufficient_qi},
        output={"gaps": list(gaps)},
    )


def _evidence_to_citation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(item.get("document_id") or ""),
        "document_name": item.get("document_name"),
        "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
        "content": item.get("content"),
        "score": item.get("score"),
    }


def _format_gap_section(gaps: list[str]) -> str:
    lines = [GAP_HEADING] + [f"- {g}" for g in gaps]
    return "\n".join(lines)


def _append_knowledge_gap(answer: str, gaps: list[str]) -> str:
    if not gaps:
        return answer
    if GAP_HEADING in answer:
        return answer
    section = _format_gap_section(gaps)
    body = (answer or "").rstrip()
    return f"{body}\n\n{section}" if body else section


def node_merge(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    pool = list(state.get("evidence") or [])
    result = merge_evidence(pool, max_evidence=MAX_EVIDENCE)
    merged = list(result.get("merged") or [])
    recorder = recorder_from_config(config)
    if recorder:
        recorder.add_span(
            "route",
            decision=merge_decision(result),
            evidence_refs=merge_evidence_refs(merged),
        )
    return {"evidence": merged}


def node_gap(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    sub_questions = list(state.get("sub_questions") or [])
    insufficient = [
        {"id": str(sq.get("id") or ""), "question": str(sq.get("question") or "")}
        for sq in sub_questions
        if str(sq.get("status") or "") == "INSUFFICIENT"
    ]
    gaps = collect_knowledge_gaps(sub_questions)
    recorder = recorder_from_config(config)
    if recorder:
        recorder.add_span(
            "route",
            decision=gap_decision(insufficient, gaps),
            rationale="补充检索额度用尽后仍不足" if gaps else "无知识缺口",
        )
    return {"knowledge_gaps": gaps}


def node_generate(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    """Final answer from merged evidence only; append Knowledge Gap when present."""
    from app import llm as llm_mod

    generate_started = time.monotonic()
    evidence = list(state.get("evidence") or [])[:MAX_EVIDENCE]
    gaps = list(state.get("knowledge_gaps") or [])
    evidence_ids = [str(e.get("id") or e.get("chunk_id") or "") for e in evidence]
    question = _user_question(state)

    llm_mod.LAST_USAGE = None
    usage: dict[str, int] | None = None
    if evidence:
        context = "\n\n".join(
            f"[{e.get('document_name')}]\n{e.get('content')}" for e in evidence
        )
        gap_hint = ""
        if gaps:
            gap_hint = (
                "\n\n以下子问题在知识库中仍无足够证据，回答中必须单独列出 Knowledge Gap，"
                "不得用外部常识补全这些缺口：\n"
                + "\n".join(f"- {g}" for g in gaps)
            )
        prompt = (
            "只根据资料作答；不要编造出处或用常识补全资料未覆盖的部分。"
            f"{gap_hint}\n\n问题：{question}"
        )
        answer = llm_mod.chat(prompt, context, history=None)
        usage = getattr(llm_mod, "LAST_USAGE", None)
    else:
        answer = "知识库中未检索到可用证据，无法就相关问题给出有依据的回答。"

    answer = _append_knowledge_gap(answer, gaps)
    citations = [_evidence_to_citation(e) for e in evidence]

    recorder = recorder_from_config(config)
    if recorder:
        metrics: dict[str, Any] = {
            "elapsed_ms": int((time.monotonic() - generate_started) * 1000),
        }
        if usage:
            metrics["tokens"] = usage
        recorder.add_span(
            "generate",
            decision=knowledge_span_decision(
                "generate",
                input={"evidence_ids": evidence_ids},
                output={"answer": (answer or "")[:120]},
            ),
            evidence_refs=merge_evidence_refs(evidence),
            metrics=metrics,
        )

    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": answer})
    updates: dict[str, Any] = {
        "answer": answer,
        "messages": messages,
        "citations": citations,
        "evidence": evidence,
    }
    if usage:
        updates["usage"] = usage
    return updates


def build_knowledge_flow_graph():
    """Knowledge Agent DAG: analyze → simple|complex → … → generate."""
    global _compiled_knowledge
    if _compiled_knowledge is not None:
        return _compiled_knowledge

    graph = StateGraph(AgentState)
    graph.add_node("analyze", node_analyze)
    graph.add_node("decompose", node_decompose)
    graph.add_node("retrieve_qi", node_retrieve_qi)
    graph.add_node("sufficiency", node_sufficiency)
    graph.add_node("rewrite", node_rewrite)
    graph.add_node("merge", node_merge)
    graph.add_node("gap", node_gap)
    graph.add_node("generate", node_generate)
    graph.add_edge(START, "analyze")
    graph.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {"retrieve_qi": "retrieve_qi", "decompose": "decompose"},
    )
    graph.add_edge("decompose", "retrieve_qi")
    graph.add_edge("retrieve_qi", "sufficiency")
    graph.add_conditional_edges(
        "sufficiency",
        route_after_sufficiency,
        {"retrieve_qi": "retrieve_qi", "rewrite": "rewrite"},
    )
    graph.add_conditional_edges(
        "rewrite",
        route_after_rewrite,
        {"retrieve_qi": "retrieve_qi", "rewrite": "rewrite", "merge": "merge"},
    )
    graph.add_edge("merge", "gap")
    graph.add_edge("gap", "generate")
    graph.add_edge("generate", END)
    _compiled_knowledge = graph.compile()
    return _compiled_knowledge


def reset_knowledge_flow_graph() -> None:
    global _compiled_knowledge
    _compiled_knowledge = None


__all__ = [
    "GAP_HEADING",
    "MAX_REWRITE_PER_Q",
    "MAX_SUB_QUESTIONS",
    "build_knowledge_flow_graph",
    "collect_knowledge_gaps",
    "gap_decision",
    "node_analyze",
    "node_decompose",
    "node_gap",
    "node_generate",
    "node_merge",
    "node_retrieve_qi",
    "node_rewrite",
    "node_sufficiency",
    "reset_knowledge_flow_graph",
    "route_after_analyze",
    "route_after_rewrite",
    "route_after_sufficiency",
]
