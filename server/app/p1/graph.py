from __future__ import annotations

import json
import uuid
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.p1.tools import search_knowledge
from app.search import SearchHit

MAX_LOOPS = 3
MAX_CITATIONS = 20

_compiled = None


class AgentState(TypedDict, total=False):
    knowledge_base_id: str | None
    task: Literal["agent", "report"]
    messages: list[dict[str, str]]
    citations: list[dict[str, Any]]
    loop_count: int
    max_loops: int
    next_action: Literal["search", "generate"]
    search_query: str
    answer: str


def _user_question(state: AgentState) -> str:
    for item in reversed(state.get("messages") or []):
        if item.get("role") == "user":
            return item.get("content") or ""
    return ""


def _hit_to_citation(hit: SearchHit) -> dict[str, Any]:
    return {
        "document_id": str(hit.document_id),
        "document_name": hit.document_name,
        "chunk_id": str(hit.chunk_id),
        "page_start": hit.page,
        "page_end": hit.page,
        "content": hit.content,
        "score": hit.score,
    }


def plan_agent_search(
    question: str,
    *,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """首轮 Agent reason：决定是否检索及 search_query（与 node_reason 第一次调用一致）。"""
    state: AgentState = {
        "messages": [{"role": "user", "content": question}],
        "citations": citations or [],
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
    }
    return reason_decide(state)


def reason_decide(state: AgentState) -> dict[str, Any]:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    cites = state.get("citations") or []
    preview = "\n".join(f"- {c.get('document_name')}: {str(c.get('content') or '')[:200]}" for c in cites[:8])
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你在决定下一步。只输出 JSON。"
                '要检索知识库：{{"action":"search","query":"检索词"}}。'
                '资料已够用或不必检索：{{"action":"generate"}}。'
                "不要编造检索结果。",
            ),
            ("human", "问题：{question}\n已有资料：\n{preview}"),
        ]
    )
    raw = str((prompt | model).invoke({"question": _user_question(state), "preview": preview or "（无）"}).content)
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
    except json.JSONDecodeError:
        return {"next_action": "generate"}
    if not isinstance(parsed, dict):
        return {"next_action": "generate"}
    if str(parsed.get("action") or "") == "search":
        query = str(parsed.get("query") or "").strip()
        if query:
            return {"next_action": "search", "search_query": query}
    return {"next_action": "generate"}


def node_reason(state: AgentState) -> dict[str, Any]:
    if int(state.get("loop_count") or 0) >= int(state.get("max_loops") or MAX_LOOPS):
        return {"next_action": "generate"}
    return reason_decide(state)


def node_run_tool(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    session = (config.get("configurable") or {}).get("session")
    user_id = (config.get("configurable") or {}).get("user_id")
    kb_raw = state.get("knowledge_base_id")
    kb_id = uuid.UUID(kb_raw) if kb_raw else None
    hits = search_knowledge(session, state.get("search_query") or "", user_id=user_id, knowledge_base_id=kb_id)
    cites = list(state.get("citations") or [])
    cites.extend(_hit_to_citation(hit) for hit in hits)
    if len(cites) > MAX_CITATIONS:
        cites = cites[-MAX_CITATIONS:]
    return {"citations": cites, "loop_count": int(state.get("loop_count") or 0) + 1}


def generate_answer(state: AgentState) -> str:
    from app.llm import chat

    messages = list(state.get("messages") or [])
    question = _user_question(state)
    prior = messages[:-1] if messages and messages[-1].get("role") == "user" else messages
    history = [
        (str(item.get("role") or ""), str(item.get("content") or ""))
        for item in prior
        if item.get("role") in ("user", "assistant") and item.get("content")
    ]
    cites = state.get("citations") or []
    context = "\n\n".join(f"[{c.get('document_name')}]\n{c.get('content')}" for c in cites)
    if state.get("task") == "report":
        question = (
            "请根据资料写成研究报告：先列简短大纲，再按「摘要 / 要点 / 依据 / 结论」分节撰写。"
            "只使用资料中的事实，不要编造出处。\n\n"
            f"主题：{question}"
        )
    return chat(question, context, history)


def node_generate(state: AgentState) -> dict[str, Any]:
    answer = generate_answer(state)
    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": answer})
    return {"answer": answer, "messages": messages}


def route_after_reason(state: AgentState) -> Literal["run_tool", "generate"]:
    if state.get("next_action") == "search" and int(state.get("loop_count") or 0) < int(
        state.get("max_loops") or MAX_LOOPS
    ):
        return "run_tool"
    return "generate"


def build_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    from app.p1.checkpoint import get_checkpointer

    graph = StateGraph(AgentState)
    graph.add_node("reason", node_reason)
    graph.add_node("run_tool", node_run_tool)
    graph.add_node("generate", node_generate)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges("reason", route_after_reason, {"run_tool": "run_tool", "generate": "generate"})
    graph.add_edge("run_tool", "reason")
    graph.add_edge("generate", END)
    _compiled = graph.compile(checkpointer=get_checkpointer())
    return _compiled


def reset_graph() -> None:
    global _compiled
    _compiled = None
    from app.p1.checkpoint import reset_checkpointer

    reset_checkpointer()


def initial_state(
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    task: Literal["agent", "report"] = "agent",
    history: list[dict[str, str]] | None = None,
) -> AgentState:
    messages = list(history or [])
    messages.append({"role": "user", "content": query})
    return {
        "knowledge_base_id": str(knowledge_base_id) if knowledge_base_id else None,
        "task": task,
        "messages": messages,
        "citations": [],
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
        "next_action": "generate",
        "search_query": "",
        "answer": "",
    }
