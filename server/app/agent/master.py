from __future__ import annotations

import uuid
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent.booking_agent import booking_initial_state
from app.agent.graph import build_graph, initial_state
from app.agent.intent import IntentLabel, classify_intent

_compiled = None



class MasterState(TypedDict, total=False):
    query: str
    task: Literal["agent", "report"]
    intent: IntentLabel
    knowledge_base_id: str | None
    conversation_id: str | None
    allow_web: bool
    history: list[dict[str, str]]
    summary: str
    ltm_hits: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    loop_count: int
    usage: dict[str, int] | None
    progress: list[str]
    travel_data: dict[str, Any]
    plan_html: dict[str, Any]
    report_url: str | None
    pending_action: dict[str, Any] | None
    hitl_confirm: bool | None
    bookings: list[dict[str, Any]]


def master_initial_state(
    query: str,
    *,
    task: Literal["agent", "report"] = "agent",
    knowledge_base_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    ltm_hits: list[dict[str, Any]] | None = None,
    allow_web: bool = False,
    pending_action: dict[str, Any] | None = None,
    hitl_confirm: bool | None = None,
) -> MasterState:
    return {
        "query": query,
        "task": task,
        "intent": "knowledge",
        "knowledge_base_id": str(knowledge_base_id) if knowledge_base_id else None,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "history": list(history or []),
        "summary": (summary or "").strip(),
        "ltm_hits": list(ltm_hits or []),
        "allow_web": bool(allow_web),
        "answer": "",
        "citations": [],
        "loop_count": 0,
        "progress": [],
        "travel_data": {},
        "plan_html": {},
        "report_url": None,
        "pending_action": pending_action,
        "hitl_confirm": hitl_confirm,
        "bookings": [],
    }


def node_intent(state: MasterState) -> dict[str, Any]:
    # HITL 确认/拒绝续聊：强制走 booking 节点以执行 pending_action
    if state.get("hitl_confirm") is not None:
        return {"intent": "booking"}
    intent = classify_intent(
        state.get("query") or "",
        task=state.get("task") or "agent",
        history_tail=list(state.get("history") or [])[-4:],
    )
    return {"intent": intent}


def route_after_intent(
    state: MasterState,
) -> Literal["knowledge", "chat", "plan", "booking"]:
    return {
        "knowledge": "knowledge",
        "plan": "plan",
        "booking": "booking",
        "chat": "chat",
    }.get(state.get("intent") or "knowledge", "knowledge")


def node_knowledge(state: MasterState, config: RunnableConfig) -> dict[str, Any]:
    inner_configurable = (config.get("configurable") or {}).get
    kb_raw = state.get("knowledge_base_id")
    convo_raw = state.get("conversation_id")
    out = build_graph().invoke(
        initial_state(
            state.get("query") or "",
            knowledge_base_id=uuid.UUID(kb_raw) if kb_raw else None,
            task=state.get("task") or "agent",
            history=list(state.get("history") or []),
            summary=state.get("summary") or "",
            ltm_hits=list(state.get("ltm_hits") or []),
            allow_web=bool(state.get("allow_web")),
        ),
        config={
            "configurable": {
                "thread_id": convo_raw or f"knowledge-{uuid.uuid4()}",
                "session": inner_configurable("session"),
                "user_id": inner_configurable("user_id"),
            }
        },
    )
    updates: dict[str, Any] = {
        "answer": out.get("answer") or "",
        "citations": list(out.get("citations") or []),
        "loop_count": int(out.get("loop_count") or 0),
        "usage": out.get("usage"),
    }
    if (state.get("task") or "agent") == "report":
        updates["report_url"] = _persist_report(convo_raw, updates["answer"])
    return updates


def _persist_report(conversation_id: str | None, answer: str) -> str | None:
    """task=report：报告 HTML 上传 MinIO reports/ 前缀；未配置/失败仅提示不影响回答。"""
    from app.travel import minio_store

    if not minio_store.minio_ready():
        return None
    html = (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>知识报告</title>"
        "<body style=\"font-family:'PingFang SC',sans-serif;max-width:820px;margin:24px auto;"
        "padding:0 16px;color:#1e293b;line-height:1.7\">"
        + answer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        + "</body></html>"
    )
    upload = minio_store.put_report_html(conversation_id, html)
    if upload:
        return upload.get("url") or upload.get("key")
    return None


def node_chat(state: MasterState) -> dict[str, Any]:
    from app import llm as llm_mod

    llm_mod.LAST_USAGE = None
    question = state.get("query") or ""
    history = [
        (str(item.get("role") or ""), str(item.get("content") or ""))
        for item in (state.get("history") or [])
        if item.get("role") in ("user", "assistant") and item.get("content")
    ]
    answer = llm_mod.chat(
        question,
        "",
        history,
        summary=(state.get("summary") or "").strip() or None,
        ltm=state.get("ltm_hits") or None,
    )
    updates: dict[str, Any] = {"answer": answer}
    usage = getattr(llm_mod, "LAST_USAGE", None)
    if usage:
        updates["usage"] = usage
    return updates


def node_plan(state: MasterState, config: RunnableConfig) -> dict[str, Any]:
    from app.agent.plan_agent import build_plan_graph, plan_initial_state

    inner_configurable = config.get("configurable") or {}
    out = build_plan_graph().invoke(
        plan_initial_state(
            state.get("query") or "",
            history=list(state.get("history") or []),
            summary=state.get("summary") or "",
            ltm_hits=list(state.get("ltm_hits") or []),
            conversation_id=state.get("conversation_id"),
            user_id=inner_configurable.get("user_id"),
        ),
        config={
            "configurable": {
                "emit": inner_configurable.get("emit"),
                "session": inner_configurable.get("session"),
                "user_id": inner_configurable.get("user_id"),
            }
        },
    )
    return {
        "answer": out.get("answer") or "",
        "citations": [],
        "progress": list(out.get("progress") or []),
        "travel_data": dict(out.get("travel_data") or {}),
        "plan_html": dict(out.get("plan_html") or {}),
    }


def node_booking(state: MasterState, config: RunnableConfig) -> dict[str, Any]:
    from app.agent.booking_agent import build_booking_graph

    inner_configurable = config.get("configurable") or {}
    out = build_booking_graph().invoke(
        booking_initial_state(
            state.get("query") or "",
            history=list(state.get("history") or []),
            summary=state.get("summary") or "",
            ltm_hits=list(state.get("ltm_hits") or []),
            conversation_id=state.get("conversation_id"),
            user_id=inner_configurable.get("user_id"),
            hitl_confirm=state.get("hitl_confirm"),
            pending_action=state.get("pending_action"),
        ),
        config={
            "configurable": {
                "emit": inner_configurable.get("emit"),
                "session": inner_configurable.get("session"),
                "user_id": inner_configurable.get("user_id"),
            }
        },
    )
    return {
        "answer": out.get("answer") or "",
        "citations": [],
        "pending_action": out.get("pending_action"),
        "bookings": list(out.get("bookings") or []),
    }


def node_finalize(state: MasterState) -> dict[str, Any]:
    updates: dict[str, Any] = {"answer": str(state.get("answer") or "")}
    if not isinstance(state.get("citations"), list):
        updates["citations"] = []
    return updates


def build_master_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    from app.agent.checkpoint import get_checkpointer

    graph = StateGraph(MasterState)
    graph.add_node("intent", node_intent)
    graph.add_node("knowledge", node_knowledge)
    graph.add_node("chat", node_chat)
    graph.add_node("plan", node_plan)
    graph.add_node("booking", node_booking)
    graph.add_node("finalize", node_finalize)
    graph.add_edge(START, "intent")
    graph.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "knowledge": "knowledge",
            "chat": "chat",
            "plan": "plan",
            "booking": "booking",
        },
    )
    for node in ("knowledge", "chat", "plan", "booking"):
        graph.add_edge(node, "finalize")
    graph.add_edge("finalize", END)
    _compiled = graph.compile(checkpointer=get_checkpointer())
    return _compiled


def reset_master_graph() -> None:
    global _compiled
    _compiled = None
    from app.agent.booking_agent import reset_booking_graph

    reset_booking_graph()
