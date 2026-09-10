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
    if len(citations) > MAX_CITATIONS:
        citations = citations[-MAX_CITATIONS:]
    if len(web_hits) > MAX_CITATIONS:
        web_hits = web_hits[-MAX_CITATIONS:]
    return citations, web_hits


def _system_prompt(state: AgentState) -> str:
    parts = [
        "你是知识库助手。需要资料时调用工具；信息足够时直接用自然语言作答，不要输出 JSON 协议。",
        "不要编造检索结果。禁止因为知识库无结果就擅自假设已联网。",
    ]
    if state.get("task") == "report":
        parts.append(
            "当前任务是研究报告：先列简短大纲，再按「摘要 / 要点 / 依据 / 结论」分节撰写；只使用资料中的事实。"
        )
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


def node_agent(state: AgentState, config: RunnableConfig = None) -> dict[str, Any]:
    tools = _bound_tools(state, config)
    model = _chat_model()
    runnable = model.bind_tools(tools) if tools else model
    prior = list(state.get("agent_messages") or [])
    invoke_messages: list[BaseMessage] = [SystemMessage(content=_system_prompt(state)), *prior]
    response = _stream_model_response(runnable, invoke_messages, _merge_runtime_config(state, config))
    if not isinstance(response, AIMessage):
        response = AIMessage(content=_message_text(response))

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
    result = _tool_node.invoke(state, runtime)
    tool_messages = list(result.get("agent_messages") or [])
    new_cites, new_web = _aggregate_from_tool_messages(tool_messages)
    cites = list(state.get("citations") or [])
    cites.extend(new_cites)
    if len(cites) > MAX_CITATIONS:
        cites = cites[-MAX_CITATIONS:]
    web_hits = list(state.get("web_hits") or [])
    web_hits.extend(new_web)
    if len(web_hits) > MAX_CITATIONS:
        web_hits = web_hits[-MAX_CITATIONS:]

    n_calls = 0
    prior = list(state.get("agent_messages") or [])
    if prior and isinstance(prior[-1], AIMessage):
        n_calls = len(list(getattr(prior[-1], "tool_calls", None) or []))

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

    return {
        "agent_messages": tool_messages,
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
