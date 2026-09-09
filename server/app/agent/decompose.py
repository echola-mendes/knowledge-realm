"""Query Decomposition — Complex path sub-questions (clip ≤5)."""

from __future__ import annotations

import json
from typing import Any

from app.agent.sufficiency import knowledge_span_decision

MAX_SUB_QUESTIONS = 5  # hard cap; prompt steers toward ≤3


def clip_sub_questions(raw: Any, *, limit: int = MAX_SUB_QUESTIONS) -> list[str]:
    """Normalize LLM / list output to non-empty question strings, hard-truncated."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("question") or item.get("q") or "").strip()
        else:
            text = str(item).strip()
        if not text:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def make_sub_questions(questions: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"q{i + 1}",
            "question": q,
            "status": "pending",
            "rewrite_count": 0,
            "evidence_ids": [],
        }
        for i, q in enumerate(questions)
    ]


def fallback_single_qi(query: str) -> list[dict[str, Any]]:
    text = (query or "").strip() or "（空问题）"
    return make_sub_questions([text])


def decompose_decision(query: str, sub_questions: list[dict[str, Any]]) -> dict[str, Any]:
    return knowledge_span_decision(
        "decompose",
        input={"query": query},
        output={
            "sub_questions": [
                {"id": sq["id"], "question": sq["question"]} for sq in sub_questions
            ]
        },
    )


def decompose_query(query: str) -> dict[str, Any]:
    """
    LLM structured decompose. On parse/empty failure → single Qi = original query.
    Returns {sub_questions, usage?}.
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
                "你在做问题分解。只输出 JSON："
                '{{"sub_questions":["子问题1","子问题2"]}}。'
                "要求：与原问相关、可独立检索、少重复。"
                "尽量不超过 3 个；绝对不要超过 5 个。"
                "若原问已是单一事实/概念，只输出一个子问题（可与原问相同）。",
            ),
            ("human", "原问：{query}"),
        ]
    )
    try:
        raw_resp = (prompt | model).invoke({"query": query})
        raw = str(raw_resp.content)
        usage = _usage_of(raw_resp)
    except Exception:
        return {"sub_questions": fallback_single_qi(query), "degraded": True}

    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
    except json.JSONDecodeError:
        return {"sub_questions": fallback_single_qi(query), "degraded": True}

    if not isinstance(parsed, dict):
        return {"sub_questions": fallback_single_qi(query), "degraded": True}

    clipped = clip_sub_questions(parsed.get("sub_questions"))
    if not clipped:
        return {"sub_questions": fallback_single_qi(query), "usage": usage, "degraded": True}
    return {"sub_questions": make_sub_questions(clipped), "usage": usage}
