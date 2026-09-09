"""Query Analysis — Simple vs Complex (knowledge Agent entry)."""

from __future__ import annotations

import json
from typing import Any, Literal

from app.agent.sufficiency import knowledge_span_decision

QueryType = Literal["simple", "complex"]


def analyze_decision(query: str, query_type: QueryType) -> dict[str, Any]:
    return knowledge_span_decision(
        "analyze",
        input={"query": query},
        output={"query_type": query_type},
    )


def _heuristic_query_type(query: str) -> QueryType:
    """Lightweight fallback when LLM fails: multi-aspect / contrast → complex."""
    text = (query or "").strip()
    if not text:
        return "simple"
    markers = ("区别", "对比", "比较", "以及", "还有", "分别", "和", "与", "？", "?")
    hits = sum(1 for m in markers if m in text)
    if hits >= 2 or text.count("？") + text.count("?") >= 2:
        return "complex"
    if any(m in text for m in ("区别", "对比", "比较")):
        return "complex"
    return "simple"


def analyze_query(query: str) -> dict[str, Any]:
    """
    Classify query_type. On LLM/parse failure → heuristic (safe, no crash).
    Returns {query_type, usage?}.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings
    from app.llm import _usage_of

    text = (query or "").strip()
    if not text:
        return {"query_type": "simple"}

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你在做检索编排前的问题分类。只输出 JSON："
                '{{"query_type":"simple"}} 或 {{"query_type":"complex"}}。'
                "simple：单事实/单概念，一次检索即可。"
                "complex：多实体对比、多知识点并列、或多个子问题，需要分解后再检索。"
                "不要回答问题本身。",
            ),
            ("human", "用户问题：{query}"),
        ]
    )
    try:
        raw_resp = (prompt | model).invoke({"query": text})
        raw = str(raw_resp.content)
        usage = _usage_of(raw_resp)
    except Exception:
        return {"query_type": _heuristic_query_type(text)}

    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
    except json.JSONDecodeError:
        return {"query_type": _heuristic_query_type(text)}

    if not isinstance(parsed, dict):
        return {"query_type": _heuristic_query_type(text)}
    qt = str(parsed.get("query_type") or "").strip().lower()
    if qt not in ("simple", "complex"):
        return {"query_type": _heuristic_query_type(text)}
    out: dict[str, Any] = {"query_type": qt}
    if usage:
        out["usage"] = usage
    return out
