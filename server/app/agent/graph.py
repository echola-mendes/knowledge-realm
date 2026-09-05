from __future__ import annotations

import json
import uuid
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent.tools import search_graph, search_knowledge, web_search
from app.search import SearchHit

MAX_LOOPS = 3
MAX_SUBTASKS = 3
MAX_CITATIONS = 20

_compiled = None


class AgentState(TypedDict, total=False):
    knowledge_base_id: str | None
    task: Literal["agent", "report"]
    messages: list[dict[str, str]]
    summary: str
    ltm_hits: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    web_hits: list[dict[str, Any]]
    loop_count: int
    max_loops: int
    next_action: Literal["search", "web", "generate"]
    search_query: str
    answer: str
    subtasks: list[str]
    subtask_index: int
    allow_web: bool
    usage: dict[str, int]


def clip_subtasks(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        out.append(text)
        if len(out) >= MAX_SUBTASKS:
            break
    return out


def _current_subtask(state: AgentState, extra_tasks: list[str] | None = None) -> str:
    tasks = extra_tasks if extra_tasks is not None else clip_subtasks(state.get("subtasks") or [])
    if not tasks:
        return ""
    idx = int(state.get("subtask_index") or 0)
    if idx < 0 or idx >= len(tasks):
        return ""
    return tasks[idx]


def _plan_preview(state: AgentState) -> str:
    tasks = clip_subtasks(state.get("subtasks") or [])
    if not tasks:
        return "（无拆分）"
    idx = int(state.get("subtask_index") or 0)
    idx = min(max(idx, 0), len(tasks) - 1)
    lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(tasks))
    return f"{lines}\n当前子任务：{tasks[idx]}"


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


def _usage_extra(usage: dict[str, int] | None) -> dict[str, Any]:
    return {"usage": usage} if usage else {}


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
    web_hits = state.get("web_hits") or []
    if web_hits:
        web_preview = "\n".join(
            f"- 网页 {h.get('title') or h.get('url')}: {str(h.get('snippet') or '')[:200]}" for h in web_hits[:8]
        )
        preview = f"{preview}\n{web_preview}".strip() if preview else web_preview
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你在决定下一步。只输出 JSON。"
                '不调用工具、直接生成：{{"action":"direct"}}。'
                '检索知识库：{{"action":"rag","query":"检索词"}}。'
                + (
                    '按知识图谱检索：{{"action":"graph","query":"检索词"}}。'
                    if state.get("knowledge_base_id")
                    else ""
                )
                + (
                    '检索互联网：{{"action":"web","query":"检索词"}}。'
                    if state.get("allow_web")
                    else "禁止检索互联网，不得输出 action=web。"
                )
                + '复杂问题仅当尚无子任务时，可加 {{"subtasks":["步骤1","步骤2"]}}（最多3条）。'
                "之后每圈只选 action，禁止再写 subtasks。"
                "不要编造检索结果。禁止因为知识库无结果就自动改为联网。",
            ),
            ("human", "问题：{question}\n子任务：\n{plan}\n已有资料：\n{preview}"),
        ]
    )
    raw_resp = (prompt | model).invoke(
        {
            "question": _user_question(state),
            "plan": _plan_preview(state),
            "preview": preview or "（无）",
        }
    )
    raw = str(raw_resp.content)
    from app.llm import _usage_of

    usage = _usage_of(raw_resp)
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
    except json.JSONDecodeError:
        return {"next_action": "generate", **_usage_extra(usage)}
    if not isinstance(parsed, dict):
        return {"next_action": "generate", **_usage_extra(usage)}
    extra: dict[str, Any] = {}
    can_write_plan = int(state.get("loop_count") or 0) == 0 and not clip_subtasks(state.get("subtasks") or [])
    if can_write_plan:
        planned = clip_subtasks(parsed.get("subtasks"))
        if planned:
            extra["subtasks"] = planned
    action = str(parsed.get("action") or "")
    query = str(parsed.get("query") or "").strip() or _current_subtask(state, extra.get("subtasks"))
    if action in ("rag", "search") and query:
        return {"next_action": "search", "search_query": query, **extra, **_usage_extra(usage)}
    if action == "graph" and query and state.get("knowledge_base_id"):
        return {"next_action": "graph", "search_query": query, **extra, **_usage_extra(usage)}
    if action == "web" and query and state.get("allow_web"):
        return {"next_action": "web", "search_query": query, **extra, **_usage_extra(usage)}
    return {"next_action": "generate", **extra, **_usage_extra(usage)}


def node_reason(state: AgentState) -> dict[str, Any]:
    if int(state.get("loop_count") or 0) >= int(state.get("max_loops") or MAX_LOOPS):
        return {"next_action": "generate"}
    existing = clip_subtasks(state.get("subtasks") or [])
    idx = int(state.get("subtask_index") or 0)
    if existing and idx >= len(existing):
        return {"next_action": "generate"}
    updates = reason_decide(state)
    if existing or int(state.get("loop_count") or 0) != 0:
        updates.pop("subtasks", None)
        return updates
    planned = clip_subtasks(updates.get("subtasks"))
    if planned:
        updates["subtasks"] = planned
    else:
        updates.pop("subtasks", None)
    return updates


def node_run_tool(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    session = (config.get("configurable") or {}).get("session")
    user_id = (config.get("configurable") or {}).get("user_id")
    kb_raw = state.get("knowledge_base_id")
    kb_id = uuid.UUID(kb_raw) if kb_raw else None
    query = state.get("search_query") or ""
    loop_count = int(state.get("loop_count") or 0) + 1
    tasks = clip_subtasks(state.get("subtasks") or [])
    idx = int(state.get("subtask_index") or 0)
    if tasks and idx < len(tasks):
        idx += 1
    if state.get("next_action") == "web":
        if not state.get("allow_web"):
            return {"loop_count": loop_count, "subtask_index": idx}
        web_hits = list(state.get("web_hits") or [])
        web_hits.extend(web_search(query))
        if len(web_hits) > MAX_CITATIONS:
            web_hits = web_hits[-MAX_CITATIONS:]
        return {"web_hits": web_hits, "loop_count": loop_count, "subtask_index": idx}
    if state.get("next_action") == "graph" and kb_id:
        hits = search_graph(session, query, user_id=user_id, knowledge_base_id=kb_id)
    else:
        hits = search_knowledge(session, query, user_id=user_id, knowledge_base_id=kb_id)
    cites = list(state.get("citations") or [])
    cites.extend(_hit_to_citation(hit) for hit in hits)
    if len(cites) > MAX_CITATIONS:
        cites = cites[-MAX_CITATIONS:]
    return {"citations": cites, "loop_count": loop_count, "subtask_index": idx}


def generate_answer(state: AgentState) -> tuple[str, dict[str, int] | None]:
    """生成回答并返回 (文本, token 用量)。经 app.llm.chat 晚绑定调用，兼容测试替换。"""
    from app import llm as llm_mod

    llm_mod.LAST_USAGE = None
    messages = list(state.get("messages") or [])
    question = _user_question(state)
    subtasks = clip_subtasks(state.get("subtasks") or [])
    if subtasks:
        listed = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(subtasks))
        question = f"请综合下列子任务的资料汇总作答。\n{listed}\n\n原问题：{question}"
    prior = messages[:-1] if messages and messages[-1].get("role") == "user" else messages
    history = [
        (str(item.get("role") or ""), str(item.get("content") or ""))
        for item in prior
        if item.get("role") in ("user", "assistant") and item.get("content")
    ]
    cites = state.get("citations") or []
    context = "\n\n".join(f"[{c.get('document_name')}]\n{c.get('content')}" for c in cites)
    web_hits = state.get("web_hits") or []
    if web_hits:
        web_block = "\n\n".join(
            f"[{h.get('title') or h.get('url')}]\n{h.get('url') or ''}\n{h.get('snippet') or ''}".strip()
            for h in web_hits
        )
        context = f"{context}\n\n{web_block}".strip() if context else web_block
    if state.get("task") == "report":
        question = (
            "请根据资料写成研究报告：先列简短大纲，再按「摘要 / 要点 / 依据 / 结论」分节撰写。"
            "只使用资料中的事实，不要编造出处。\n\n"
            f"主题：{question}"
        )
    answer = llm_mod.chat(
        question,
        context,
        history,
        summary=(state.get("summary") or "").strip() or None,
        ltm=state.get("ltm_hits") or None,
    )
    return answer, getattr(llm_mod, "LAST_USAGE", None)


def node_generate(state: AgentState) -> dict[str, Any]:
    result = generate_answer(state)
    answer, usage = result if isinstance(result, tuple) else (result, None)
    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": answer})
    updates: dict[str, Any] = {"answer": answer, "messages": messages}
    if usage:
        updates["usage"] = usage
    return updates


def route_after_reason(state: AgentState) -> Literal["run_tool", "generate"]:
    action = state.get("next_action")
    if action == "web" and not state.get("allow_web"):
        return "generate"
    if action in ("search", "rag", "web", "graph") and int(state.get("loop_count") or 0) < int(
        state.get("max_loops") or MAX_LOOPS
    ):
        return "run_tool"
    return "generate"


def build_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    from app.agent.checkpoint import get_checkpointer

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
    from app.agent.checkpoint import reset_checkpointer

    reset_checkpointer()


def initial_state(
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    task: Literal["agent", "report"] = "agent",
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    ltm_hits: list[dict[str, Any]] | None = None,
    allow_web: bool = False,
) -> AgentState:
    messages = list(history or [])
    messages.append({"role": "user", "content": query})
    return {
        "knowledge_base_id": str(knowledge_base_id) if knowledge_base_id else None,
        "task": task,
        "messages": messages,
        "summary": (summary or "").strip(),
        "ltm_hits": list(ltm_hits or []),
        "citations": [],
        "web_hits": [],
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
        "next_action": "generate",
        "search_query": "",
        "answer": "",
        "subtasks": [],
        "subtask_index": 0,
        "allow_web": bool(allow_web),
    }
