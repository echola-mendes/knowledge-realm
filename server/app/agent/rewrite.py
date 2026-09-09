"""Query Rewrite for INSUFFICIENT Qi (supplementary retrieve)."""

from __future__ import annotations

import json
from typing import Any

from app.agent.sufficiency import knowledge_span_decision

MAX_REWRITE_PER_Q = 2


def rewrite_decision(
    *,
    qi_id: str,
    from_query: str,
    to_query: str,
    reason: str = "",
    skipped: bool = False,
) -> dict[str, Any]:
    return knowledge_span_decision(
        "rewrite",
        input={
            "qi_id": qi_id,
            "from_query": from_query,
            "reason": reason or "INSUFFICIENT",
        },
        output={"to_query": to_query, "skipped_duplicate": skipped},
    )


def rewrite_query(qi_question: str, *, user_query: str = "") -> dict[str, Any]:
    """
    LLM rewrite for a single Qi. On failure returns the original qi_question
    (caller may then skip Tool via searched_queries dedup).
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings
    from app.llm import _usage_of

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
                "你在改写检索词。只输出 JSON：{{\"query\":\"改写后的检索词\"}}。"
                "不改变用户意图；优先补全缺失实体/术语，便于知识库检索。"
                "不要回答问题本身。",
            ),
            (
                "human",
                "用户原问：{user_query}\n不足的子问题：{qi_question}\n请给出更好的检索词。",
            ),
        ]
    )
    try:
        raw_resp = (prompt | model).invoke(
            {"user_query": user_query or qi_question, "qi_question": qi_question}
        )
        raw = str(raw_resp.content)
        usage = _usage_of(raw_resp)
    except Exception:
        return {"query": qi_question}

    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
    except json.JSONDecodeError:
        return {"query": qi_question}

    if not isinstance(parsed, dict):
        return {"query": qi_question}
    to_query = str(parsed.get("query") or "").strip()
    if not to_query:
        return {"query": qi_question, "usage": usage}
    return {"query": to_query, "usage": usage}
