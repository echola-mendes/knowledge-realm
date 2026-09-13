from __future__ import annotations

import json
import uuid
from typing import Any, Literal, Mapping, Sequence

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.react_evidence import process_react_tool_round
from app.agent.state import ReactState, user_question
from app.agent.tools import tools_for
from app.agent.tools.registry import AGENT_TOOLS
from app.audit.recorder import recorder_from_config

MAX_LOOPS = 3
MAX_TOOL_CALLS = 6
MAX_CITATIONS = 20

_compiled = None

# Compat alias for older imports; prefer ReactState.
AgentState = ReactState


def _user_question(state: ReactState) -> str:
    return user_question(state)


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


def _system_prompt(state: ReactState) -> str:
    parts = [
        "你是一个 ReAct 知识 Agent。",
        "",
        "核心判定：证据是否「足够」以本轮 Tool Observation 中的 [Evidence Sufficiency] / sufficiency 字段为准；",
        "有命中≠充分。会话历史与长期记忆只作对话上下文，禁止当作本轮检索证据，也禁止用历史旧答冒充本轮已检索。",
        "",
        "处理问题时遵循：",
        "1. 需要库内/外部/结构化事实时，先调用合适 Tool；无本轮 Observation 不得点名虚构文档来源。",
        "2. 每轮仅基于本轮 Tool Observation + Sufficiency 再决策：直接终答 / 换 Tool / 改写 query 再调同一 Tool / 交叉验证另一来源 / 停止并说明不足。",
        "3. sufficient=false：优先针对 missing_aspects / gaps 改写 query 补搜；禁止精确重复 Observation 中 searched_queries 已有 Query；勿泛化重搜原问题。",
        "4. sufficient=true：可整理证据作答；仍受工具预算与安全限制约束。",
        "5. 某 Qi rewrite_count 已达上限（rewrite_remaining=0）或工具预算耗尽且仍不足：勿再盲目改写补搜；允许回答，但必须明确列出 knowledge_gaps / 未覆盖方面，禁止伪装已充分。",
        "6. 多来源冲突时继续检索交叉验证，或在终答中明确说明冲突；勿静默择一编造。",
        "7. 不要编造检索结果；知识库无命中时如实说明，禁止擅自假设已联网。不要输出 JSON 协议。",
    ]
    if state.get("task") == "report":
        parts.append(
            "当前任务是研究报告：先列简短大纲，再按「摘要 / 要点 / 依据 / 结论」分节撰写；只使用资料中的事实。"
        )
    if state.get("allow_web"):
        parts.append("当前 allow_web=true，必要时可使用 web_search。")
    else:
        parts.append("当前 allow_web=false，禁止调用 web_search。")

    sub_questions = state.get("sub_questions") or []
    if sub_questions:
        lines = []
        for sq in sub_questions[:8]:
            lines.append(
                f"- {sq.get('id')}: {sq.get('question')} "
                f"[status={sq.get('status')}, rewrite={sq.get('rewrite_count') or 0}]"
            )
        parts.append("当前子问题 Qi：\n" + "\n".join(lines))
    gaps = state.get("knowledge_gaps") or []
    if gaps:
        parts.append("knowledge_gaps：\n" + "\n".join(f"- {g}" for g in gaps[:12]))
    suf = state.get("sufficiency") or {}
    if suf:
        parts.append(
            "最近 Sufficiency："
            f"sufficient={suf.get('sufficient')} precheck={suf.get('precheck')} "
            f"qi_id={suf.get('qi_id')} "
            f"rewrite={suf.get('rewrite_count')}/{suf.get('rewrite_remaining')}"
        )
        missing = list(suf.get("missing_aspects") or [])
        if missing:
            parts.append("missing_aspects：\n" + "\n".join(f"- {m}" for m in missing[:8]))
    searched = state.get("searched_queries") or []
    if searched:
        parts.append(
            "已检索 query（禁止精确重复）：\n"
            + "\n".join(f"- {q}" for q in list(searched)[:12])
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


def _remaining_tool_budget(state: ReactState) -> int:
    return max(0, MAX_TOOL_CALLS - int(state.get("tool_call_count") or 0))


def _ai_with_tool_calls(message: AIMessage, tool_calls: list[dict[str, Any]]) -> AIMessage:
    # Empty tool_calls is falsy; AIMessage would then rehydrate from additional_kwargs.
    extra = dict(getattr(message, "additional_kwargs", None) or {})
    extra.pop("tool_calls", None)
    extra.pop("function_call", None)
    return AIMessage(
        content=message.content,
        tool_calls=tool_calls,
        invalid_tool_calls=[],
        id=getattr(message, "id", None),
        additional_kwargs=extra,
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


def _bound_tools(state: ReactState, config: RunnableConfig | None):
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


def _merge_runtime_config(state: ReactState, config: RunnableConfig | None) -> RunnableConfig:
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


def _safe_tool_result_reason(
    tool_names: Sequence[str],
    hits: int,
    sufficiency: Mapping[str, Any] | None = None,
) -> str:
    name = next((n for n in tool_names if n), "")
    n = max(0, int(hits))
    if name == "search_knowledge":
        hit = f"命中{n}条"
    elif name == "search_graph":
        hit = f"图谱命中{n}条"
    elif name == "web_search":
        hit = f"联网{n}条"
    elif name == "text2sql":
        hit = "结构化查询完成"
    else:
        hit = f"返回{n}条"

    suf = sufficiency or {}
    if suf.get("sufficient") is True:
        text = f"{hit}；证据充分"
    elif suf:
        missing = list(suf.get("missing_aspects") or [])
        gaps = list(suf.get("gaps") or [])
        tip = ""
        if missing:
            tip = str(missing[0]).strip()
        elif gaps:
            tip = str(gaps[0]).strip()
        if tip:
            # Keep short for SSE reason budget.
            tip = tip.replace("missing_aspect: ", "").replace("rewrite budget exhausted", "改写额度用尽")
            if len(tip) > 12:
                tip = tip[:12]
            text = f"{hit}；证据不足，缺{tip}"
        else:
            text = f"{hit}；证据不足"
    else:
        text = hit
    return text[:40]


def node_agent(state: ReactState, config: RunnableConfig = None) -> dict[str, Any]:
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


def node_tools(state: ReactState, config: RunnableConfig = None) -> dict[str, Any]:
    runtime = _merge_runtime_config(state, config)
    remaining = _remaining_tool_budget(state)
    msgs = list(state.get("agent_messages") or [])
    if remaining <= 0:
        out_messages: list[AnyMessage] = []
        if msgs and isinstance(msgs[-1], AIMessage):
            stripped = _truncate_tool_calls(msgs[-1], 0)
            if stripped is not msgs[-1]:
                out_messages = [stripped]
        return {
            "agent_messages": out_messages,
            "citations": list(state.get("citations") or []),
            "web_hits": list(state.get("web_hits") or []),
            "loop_count": int(state.get("loop_count") or 0),
            "tool_call_count": int(state.get("tool_call_count") or 0),
        }
    if msgs and isinstance(msgs[-1], AIMessage):
        truncated = _truncate_tool_calls(msgs[-1], remaining)
        work_state: ReactState = {**state, "agent_messages": msgs[:-1] + [truncated]}
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

    out_messages: list[AnyMessage] = list(tool_messages)
    if msgs and isinstance(msgs[-1], AIMessage):
        truncated = _truncate_tool_calls(msgs[-1], remaining)
        orig_calls = list(getattr(msgs[-1], "tool_calls", None) or [])
        kept_calls = list(getattr(truncated, "tool_calls", None) or [])
        if kept_calls != orig_calls:
            # Same id → add_messages replaces the over-budget AIMessage.
            out_messages = [truncated, *tool_messages]

    # Evidence pool + rule precheck + LLM sufficiency (not a Workflow node).
    ai_for_args: AIMessage | None = None
    for msg in reversed(msgs):
        if isinstance(msg, AIMessage) and (getattr(msg, "tool_calls", None) or []):
            ai_for_args = msg
            break
    ev_updates = process_react_tool_round(
        {
            **state,
            "citations": cites,
            "web_hits": web_hits,
        },
        [m for m in out_messages if isinstance(m, ToolMessage)],
        ai_message=ai_for_args,
        user_question=_user_question(state),
    )
    patched_tools = list(ev_updates.get("agent_messages") or [])
    # Preserve any truncated AIMessage prefix in out_messages.
    prefix = [m for m in out_messages if not isinstance(m, ToolMessage)]
    out_messages = prefix + patched_tools
    sufficiency = ev_updates.get("sufficiency") or {}

    recorder = recorder_from_config(config)
    if recorder:
        for msg in patched_tools:
            if not isinstance(msg, ToolMessage):
                continue
            payload = _parse_tool_payload(_message_text(msg))
            suf_payload = payload.get("sufficiency") if isinstance(payload.get("sufficiency"), dict) else sufficiency
            missing = list(suf_payload.get("missing_aspects") or [])[:6]
            covered = list(suf_payload.get("covered_aspects") or [])[:6]
            gaps_short = [str(g)[:80] for g in list(suf_payload.get("gaps") or [])[:4]]
            recorder.add_span(
                "tool_result",
                decision={
                    "tool": getattr(msg, "name", None) or "tool",
                    "tool_call_id": getattr(msg, "tool_call_id", None),
                    "preview": str(payload.get("text") or "")[:120],
                    "sufficient": bool(suf_payload.get("sufficient")),
                    "qi_id": suf_payload.get("qi_id"),
                    "missing": missing,
                    "covered": covered,
                    "gaps": gaps_short,
                },
                metrics={"hits": len(payload.get("citations") or payload.get("web_hits") or [])},
            )

    writer = _stream_writer()
    if writer:
        tool_names = [
            str(getattr(msg, "name", None) or "tool")
            for msg in patched_tools
            if isinstance(msg, ToolMessage)
        ]
        round_hits = len(new_cites) + len(new_web)
        writer(
            {
                "type": "tool_result",
                "reason": _safe_tool_result_reason(tool_names, round_hits, sufficiency),
                "hits": len(cites) + len(web_hits),
                "loop_count": loop_count,
            }
        )

    result: dict[str, Any] = {
        "agent_messages": out_messages,
        "citations": cites,
        "web_hits": web_hits,
        "loop_count": loop_count,
        "tool_call_count": tool_call_count,
        "evidence": ev_updates.get("evidence") or [],
        "sub_questions": ev_updates.get("sub_questions") or state.get("sub_questions") or [],
        "knowledge_gaps": ev_updates.get("knowledge_gaps") or [],
        "searched_queries": ev_updates.get("searched_queries") or [],
        "sufficiency": sufficiency,
    }
    if ev_updates.get("usage"):
        result["usage"] = ev_updates["usage"]
    return result


def route_after_agent(state: ReactState) -> Literal["tools", "__end__"]:
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

    graph = StateGraph(ReactState)
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


def _bootstrap_react_qi(query: str) -> dict[str, Any]:
    """One-shot analyze + optional decompose before the ReAct loop (not a graph node)."""
    from app.agent.analyze import analyze_query
    from app.agent.decompose import MAX_SUB_QUESTIONS, decompose_query, fallback_single_qi

    text = (query or "").strip()
    analyzed = analyze_query(text)
    query_type = str(analyzed.get("query_type") or "simple").strip().lower()
    if query_type not in ("simple", "complex"):
        query_type = "simple"

    usage: dict[str, int] = {}
    raw_usage = analyzed.get("usage")
    if isinstance(raw_usage, dict):
        usage = {str(k): int(v) for k, v in raw_usage.items() if isinstance(v, (int, float))}

    if query_type == "simple":
        sub_questions = fallback_single_qi(text)
    else:
        result = decompose_query(text)
        sub_questions = list(result.get("sub_questions") or fallback_single_qi(text))
        if len(sub_questions) > MAX_SUB_QUESTIONS:
            sub_questions = sub_questions[:MAX_SUB_QUESTIONS]
        degraded = bool(result.get("degraded")) or not sub_questions
        if degraded:
            sub_questions = fallback_single_qi(text)
            query_type = "simple"
        dec_usage = result.get("usage")
        if isinstance(dec_usage, dict):
            for k, v in dec_usage.items():
                if isinstance(v, (int, float)):
                    usage[str(k)] = usage.get(str(k), 0) + int(v)

    out: dict[str, Any] = {
        "query_type": query_type,  # type: ignore[dict-item]
        "sub_questions": sub_questions,
        "evidence": [],
        "knowledge_gaps": [],
        "searched_queries": [],
        "sufficiency": {},
    }
    if usage:
        out["usage"] = usage
    return out


def initial_state(
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    task: Literal["agent", "report"] = "agent",
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    ltm_hits: list[dict[str, Any]] | None = None,
    allow_web: bool = False,
) -> ReactState:
    messages = list(history or [])
    messages.append({"role": "user", "content": query})
    agent_messages = _history_to_lc(history)
    agent_messages.append(HumanMessage(content=query))
    qi_boot = _bootstrap_react_qi(query)
    return {
        "knowledge_base_id": str(knowledge_base_id) if knowledge_base_id else None,
        "task": task,
        "messages": messages,
        "agent_messages": agent_messages,
        "summary": (summary or "").strip(),
        "ltm_hits": list(ltm_hits or []),
        "citations": [],
        "web_hits": [],
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
        "tool_call_count": 0,
        "answer": "",
        "allow_web": bool(allow_web),
        **qi_boot,
    }
