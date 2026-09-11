from __future__ import annotations

import json
import uuid
from typing import Annotated, Any, Literal, Sequence, TypedDict

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.tools import tools_for
from app.agent.tools.registry import AGENT_TOOLS
from app.audit.recorder import recorder_from_config

MAX_LOOPS = 3
MAX_TOOL_CALLS = 6
MAX_CITATIONS = 20

_compiled = None


class AgentState(TypedDict, total=False):
    knowledge_base_id: str | None
    task: Literal["agent", "report"]
    messages: list[dict[str, str]]
    agent_messages: Annotated[Sequence[AnyMessage], add_messages]
    summary: str
    ltm_hits: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    web_hits: list[dict[str, Any]]
    loop_count: int
    max_loops: int
    tool_call_count: int
    answer: str
    allow_web: bool
    usage: dict[str, int]
    # knowledge_flow rewrite 检索词（共享 AgentState 通道）
    search_query: str
    # Sufficiency V0 / knowledge flow (shared AgentState)
    query_type: Literal["simple", "complex"]
    sub_questions: list[dict[str, Any]]
    searched_queries: list[str]
    knowledge_gaps: list[str]
    current_qi_index: int
    last_qi_hits: int
    retrieve_phase: Literal["initial", "rewrite"]
    skip_retrieve: bool
    next_flow: str


def _user_question(state: AgentState) -> str:
    for item in reversed(state.get("messages") or []):
        if isinstance(item, dict) and item.get("role") == "user":
            return item.get("content") or ""
    for item in reversed(list(state.get("agent_messages") or [])):
        if isinstance(item, HumanMessage):
            content = item.content
            return content if isinstance(content, str) else str(content)
    return ""


def _history_to_lc(history: list[dict[str, str]] | None) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for item in history or []:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if not content:
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


def _message_text(message: BaseMessage | None) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content or "")


def _parse_tool_payload(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"text": text}
    return data if isinstance(data, dict) else {"text": text}


def _citation_key(cite: dict[str, Any]) -> tuple[str, str]:
    return (str(cite.get("document_id") or ""), str(cite.get("chunk_id") or ""))


def _citation_score(cite: dict[str, Any]) -> float | None:
    raw = cite.get("score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _merge_citations(
    items: Sequence[dict[str, Any]],
    *,
    limit: int = MAX_CITATIONS,
) -> list[dict[str, Any]]:
    """Dedup by (document_id, chunk_id); keep higher score; top-N by score.

    Missing score is lowest and keeps first-seen order. Scored items are taken
    first (score desc, first-seen on tie); remaining slots fill with unscored
    items in first-seen order. Total length ≤ limit.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for cite in items:
        if not isinstance(cite, dict):
            continue
        key = _citation_key(cite)
        prev = best.get(key)
        if prev is None:
            best[key] = cite
            order.append(key)
            continue
        new_s = _citation_score(cite)
        old_s = _citation_score(prev)
        if new_s is None:
            continue
        if old_s is None or new_s > old_s:
            best[key] = cite

    scored: list[tuple[float, int, dict[str, Any]]] = []
    unscored: list[dict[str, Any]] = []
    for i, key in enumerate(order):
        cite = best[key]
        score = _citation_score(cite)
        if score is None:
            unscored.append(cite)
        else:
            scored.append((score, i, cite))
    scored.sort(key=lambda row: (-row[0], row[1]))
    selected = [cite for _, _, cite in scored[:limit]]
    if len(selected) < limit:
        selected.extend(unscored[: limit - len(selected)])
    return selected


def _aggregate_from_tool_messages(messages: Sequence[AnyMessage]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    citations: list[dict[str, Any]] = []
    web_hits: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        payload = _parse_tool_payload(_message_text(msg))
        for cite in payload.get("citations") or []:
            if isinstance(cite, dict):
                citations.append(cite)
        for hit in payload.get("web_hits") or []:
            if isinstance(hit, dict):
                web_hits.append(hit)
    citations = _merge_citations(citations)
    if len(web_hits) > MAX_CITATIONS:
        web_hits = web_hits[-MAX_CITATIONS:]
    return citations, web_hits


def _system_prompt(state: AgentState) -> str:
    parts = [
        "你是一个 ReAct 知识 Agent。",
        "",
        "核心判定：证据是否「足够」= 本轮 Tool Observation 是否足够回答当前问题；",
        "会话历史与长期记忆只作对话上下文，禁止当作本轮检索证据，也禁止用历史旧答冒充本轮已检索。",
        "",
        "处理问题时遵循：",
        "1. 需要库内/外部/结构化事实时，先调用合适 Tool；无本轮 Observation 不得点名虚构文档来源。",
        "2. 每轮仅基于本轮 Tool Observation 再决策：直接终答 / 换 Tool / 改写 query 再调同一 Tool / 交叉验证另一来源 / 停止并说明不足。",
        "3. 命中不足或跑题：优先改写 query 重试；仍不足再换其他知识库 Tool；勿重复等价检索。",
        "4. 多来源冲突时继续检索交叉验证，或在终答中明确说明冲突；勿静默择一编造。",
        "5. 本轮 Observation 已足够则立即停止调 Tool 并自然语言作答；不要输出 JSON 协议。",
        "6. 不要编造检索结果；知识库无命中时如实说明，禁止擅自假设已联网。",
    ]
    if state.get("task") == "report":
        parts.append(
            "当前任务是研究报告：先列简短大纲，再按「摘要 / 要点 / 依据 / 结论」分节撰写；只使用资料中的事实。"
        )
    if state.get("allow_web"):
        parts.append("当前 allow_web=true，必要时可使用 web_search。")
    else:
        parts.append("当前 allow_web=false，禁止调用 web_search。")
    summary = (state.get("summary") or "").strip()
    if summary:
        parts.append(f"会话摘要：{summary}")
    ltm = state.get("ltm_hits") or []
    if ltm:
        lines = "\n".join(f"- {item.get('kind')}: {item.get('content')}" for item in ltm[:8])
        parts.append(f"长期记忆：\n{lines}")
    return "\n".join(parts)


def _chat_model():
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )


def _remaining_tool_budget(state: AgentState) -> int:
    return max(0, MAX_TOOL_CALLS - int(state.get("tool_call_count") or 0))


def _ai_with_tool_calls(message: AIMessage, tool_calls: list[dict[str, Any]]) -> AIMessage:
    return AIMessage(
        content=message.content,
        tool_calls=tool_calls,
        id=getattr(message, "id", None),
        additional_kwargs=dict(getattr(message, "additional_kwargs", None) or {}),
        response_metadata=dict(getattr(message, "response_metadata", None) or {}),
        usage_metadata=getattr(message, "usage_metadata", None),
    )


def _truncate_tool_calls(message: AIMessage, remaining: int) -> AIMessage:
    """Keep at most `remaining` tool_calls so execution cannot exceed MAX_TOOL_CALLS."""
    tool_calls = list(getattr(message, "tool_calls", None) or [])
    if remaining <= 0:
        if not tool_calls:
            return message
        return _ai_with_tool_calls(message, [])
    if len(tool_calls) <= remaining:
        return message
    return _ai_with_tool_calls(message, tool_calls[:remaining])


def _bind_model_tools(model, tools):
    """Prefer disabling parallel tool calls; fall back if the client rejects the kwarg."""
    try:
        return model.bind_tools(tools, parallel_tool_calls=False)
    except TypeError:
        return model.bind_tools(tools)


def _bound_tools(state: AgentState, config: RunnableConfig | None):
    loop_count = int(state.get("loop_count") or 0)
    tool_call_count = int(state.get("tool_call_count") or 0)
    max_loops = int(state.get("max_loops") or MAX_LOOPS)
    if loop_count >= max_loops or tool_call_count >= MAX_TOOL_CALLS:
        return []
    allow_web = bool(state.get("allow_web"))
    cfg = (config or {}).get("configurable") or {}
    kb = state.get("knowledge_base_id") or cfg.get("knowledge_base_id")
    enable_graph = bool(kb)
    return tools_for(allow_web=allow_web, enable_graph=enable_graph)


def _merge_runtime_config(state: AgentState, config: RunnableConfig | None) -> RunnableConfig:
    base = dict(config or {})
    cfg = dict(base.get("configurable") or {})
    if "knowledge_base_id" not in cfg and state.get("knowledge_base_id"):
        try:
            cfg["knowledge_base_id"] = uuid.UUID(str(state["knowledge_base_id"]))
        except (ValueError, TypeError):
            cfg["knowledge_base_id"] = state.get("knowledge_base_id")
    if "allow_web" not in cfg:
        cfg["allow_web"] = bool(state.get("allow_web"))
    base["configurable"] = cfg
    return base  # type: ignore[return-value]


def _merge_ai_chunks(chunks: list[AIMessageChunk]) -> AIMessage:
    merged: AIMessageChunk = chunks[0]
    for part in chunks[1:]:
        merged = merged + part
    tool_calls = list(getattr(merged, "tool_calls", None) or [])
    return AIMessage(
        content=merged.content,
        tool_calls=tool_calls,
        id=getattr(merged, "id", None),
        additional_kwargs=dict(getattr(merged, "additional_kwargs", None) or {}),
        response_metadata=dict(getattr(merged, "response_metadata", None) or {}),
        usage_metadata=getattr(merged, "usage_metadata", None),
    )


def _stream_model_response(runnable, messages: list[BaseMessage], config: RunnableConfig) -> AIMessage:
    """Stream model tokens; push custom SSE tokens when not a tool-call round."""
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None

    stream_fn = getattr(runnable, "stream", None)
    if stream_fn is None:
        response = runnable.invoke(messages, config=config)
        return response if isinstance(response, AIMessage) else AIMessage(content=_message_text(response))

    chunks: list[AIMessageChunk] = []
    saw_tool_chunks = False
    for chunk in stream_fn(messages, config=config):
        if isinstance(chunk, AIMessageChunk):
            chunks.append(chunk)
            if chunk.tool_call_chunks or getattr(chunk, "tool_calls", None):
                saw_tool_chunks = True
            text = chunk.content if isinstance(chunk.content, str) else ""
            if writer and text and not saw_tool_chunks:
                writer({"type": "token", "text": text})
            continue
        if isinstance(chunk, AIMessage):
            return chunk
        return AIMessage(content=_message_text(chunk))

    if not chunks:
        return AIMessage(content="")
    return _merge_ai_chunks(chunks)


def _stream_writer():
    try:
        return get_stream_writer()
    except Exception:
        return None


_TOOL_CALL_REASON = {
    "search_knowledge": "正在检索知识库",
    "search_graph": "正在检索知识图谱",
    "web_search": "正在联网搜索",
    "text2sql": "正在查询结构化数据",
}


def _tool_names_from_calls(tool_calls: Sequence[Any]) -> list[str]:
    names: list[str] = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            names.append(str(tc.get("name") or ""))
        else:
            names.append(str(getattr(tc, "name", "") or ""))
    return names


def _safe_tool_call_reason(tool_calls: Sequence[Any]) -> str:
    names = [n for n in _tool_names_from_calls(tool_calls) if n]
    if len(names) == 1 and names[0] in _TOOL_CALL_REASON:
        text = _TOOL_CALL_REASON[names[0]]
    else:
        text = "正在调用工具"
    return text[:40]


def _safe_tool_result_reason(tool_names: Sequence[str], hits: int) -> str:
    name = next((n for n in tool_names if n), "")
    n = max(0, int(hits))
    if name == "search_knowledge":
        text = f"知识库命中 {n} 条"
    elif name == "search_graph":
        text = f"图谱命中 {n} 条"
    elif name == "web_search":
        text = f"联网结果 {n} 条"
    elif name == "text2sql":
        text = "已完成结构化查询"
    else:
        text = f"工具已返回 {n} 条"
    return text[:40]


def node_agent(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    tools = _bound_tools(state, config)
    model = _chat_model()
    runnable = _bind_model_tools(model, tools) if tools else model
    prior = list(state.get("agent_messages") or [])
    invoke_messages: list[BaseMessage] = [SystemMessage(content=_system_prompt(state)), *prior]
    response = _stream_model_response(runnable, invoke_messages, _merge_runtime_config(state, config))
    if not isinstance(response, AIMessage):
        response = AIMessage(content=_message_text(response))
    response = _truncate_tool_calls(response, _remaining_tool_budget(state))

    usage = None
    try:
        from app.llm import _usage_of

        usage = _usage_of(response)
    except Exception:
        usage = None

    updates: dict[str, Any] = {"agent_messages": [response]}
    if usage:
        updates["usage"] = usage

    tool_calls = list(getattr(response, "tool_calls", None) or [])
    recorder = recorder_from_config(config)
    if tool_calls:
        writer = _stream_writer()
        if writer:
            writer(
                {
                    "type": "tool_call",
                    "reason": _safe_tool_call_reason(tool_calls),
                    "tool_calls": [
                        {"name": tc.get("name"), "args": tc.get("args") or {}, "id": tc.get("id")}
                        for tc in tool_calls
                    ],
                }
            )
        if recorder:
            recorder.add_span(
                "tool_call",
                decision={
                    "tool_calls": [
                        {"name": tc.get("name"), "args": tc.get("args") or {}, "id": tc.get("id")}
                        for tc in tool_calls
                    ]
                },
                rationale="model tool_calls",
                metrics=usage,
            )
        return updates

    answer = _message_text(response).strip()
    cites, web_hits = _aggregate_from_tool_messages(prior)
    if cites:
        updates["citations"] = cites
    if web_hits:
        updates["web_hits"] = web_hits
    messages = list(state.get("messages") or [])
    messages.append({"role": "assistant", "content": answer})
    updates["answer"] = answer
    updates["messages"] = messages
    if recorder:
        recorder.add_span(
            "generate",
            decision={"summary": answer[:120]},
            metrics=usage,
        )
    return updates


_tool_node = ToolNode(AGENT_TOOLS, messages_key="agent_messages")


def node_tools(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    runtime = _merge_runtime_config(state, config)
    remaining = _remaining_tool_budget(state)
    msgs = list(state.get("agent_messages") or [])
    if msgs and isinstance(msgs[-1], AIMessage):
        truncated = _truncate_tool_calls(msgs[-1], remaining)
        work_state: AgentState = {**state, "agent_messages": msgs[:-1] + [truncated]}
    else:
        work_state = state
    result = _tool_node.invoke(work_state, runtime)
    tool_messages = list(result.get("agent_messages") or [])
    new_cites, new_web = _aggregate_from_tool_messages(tool_messages)
    cites = _merge_citations(list(state.get("citations") or []) + new_cites)
    web_hits = list(state.get("web_hits") or [])
    web_hits.extend(new_web)
    if len(web_hits) > MAX_CITATIONS:
        web_hits = web_hits[-MAX_CITATIONS:]

    n_calls = sum(1 for msg in tool_messages if isinstance(msg, ToolMessage))
    n_calls = min(n_calls, remaining)

    loop_count = int(state.get("loop_count") or 0) + 1
    tool_call_count = int(state.get("tool_call_count") or 0) + n_calls

    recorder = recorder_from_config(config)
    if recorder:
        for msg in tool_messages:
            if not isinstance(msg, ToolMessage):
                continue
            payload = _parse_tool_payload(_message_text(msg))
            recorder.add_span(
                "tool_result",
                decision={
                    "tool": getattr(msg, "name", None) or "tool",
                    "tool_call_id": getattr(msg, "tool_call_id", None),
                    "preview": str(payload.get("text") or "")[:120],
                },
                metrics={"hits": len(payload.get("citations") or payload.get("web_hits") or [])},
            )

    out_messages: list[AnyMessage] = list(tool_messages)
    if msgs and isinstance(msgs[-1], AIMessage):
        truncated = _truncate_tool_calls(msgs[-1], remaining)
        orig_calls = list(getattr(msgs[-1], "tool_calls", None) or [])
        kept_calls = list(getattr(truncated, "tool_calls", None) or [])
        if kept_calls != orig_calls:
            # Same id → add_messages replaces the over-budget AIMessage.
            out_messages = [truncated, *tool_messages]

    writer = _stream_writer()
    if writer:
        tool_names = [
            str(getattr(msg, "name", None) or "tool")
            for msg in tool_messages
            if isinstance(msg, ToolMessage)
        ]
        round_hits = len(new_cites) + len(new_web)
        writer(
            {
                "type": "tool_result",
                "reason": _safe_tool_result_reason(tool_names, round_hits),
                "hits": len(cites) + len(web_hits),
                "loop_count": loop_count,
            }
        )

    return {
        "agent_messages": out_messages,
        "citations": cites,
        "web_hits": web_hits,
        "loop_count": loop_count,
        "tool_call_count": tool_call_count,
    }


def route_after_agent(state: AgentState) -> Literal["tools", "__end__"]:
    return tools_condition(state, messages_key="agent_messages")


def plan_agent_search(
    question: str,
    *,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """retrieval_debug：单次 bind_tools 探测是否应检索；兼容 next_action/search_query。"""
    _ = citations
    model = _chat_model().bind_tools(tools_for(allow_web=False, enable_graph=False))
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "判断是否需要检索知识库。需要则调用 search_knowledge；"
                    "不需要则直接简短说明原因，不要调用工具。"
                )
            ),
            HumanMessage(content=question),
        ]
    )
    tool_calls = list(getattr(response, "tool_calls", None) or [])
    for tc in tool_calls:
        if tc.get("name") == "search_knowledge":
            args = tc.get("args") or {}
            query = str(args.get("query") or "").strip() or question
            return {"next_action": "search", "search_query": query}
    return {"next_action": "generate", "search_query": ""}


def build_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    from app.agent.checkpoint import get_checkpointer

    graph = StateGraph(AgentState)
    graph.add_node("agent", node_agent)
    graph.add_node("tools", node_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "__end__": END})
    graph.add_edge("tools", "agent")
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
    agent_messages = _history_to_lc(history)
    agent_messages.append(HumanMessage(content=query))
    return {
        "knowledge_base_id": str(knowledge_base_id) if knowledge_base_id else None,
        "task": task,
        "messages": messages,
        "agent_messages": agent_messages,
        "summary": (summary or "").strip(),
        "ltm_hits": list(ltm_hits or []),
        "citations": [],
        "evidence": [],
        "web_hits": [],
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
        "tool_call_count": 0,
        "answer": "",
        "search_query": "",
        "allow_web": bool(allow_web),
        "query_type": "complex",
        "sub_questions": [],
        "searched_queries": [],
        "knowledge_gaps": [],
        "current_qi_index": 0,
        "last_qi_hits": 0,
    }
