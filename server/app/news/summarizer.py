from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.config import get_settings
from app.llm import llm_keys_ready

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Double braces so ChatPromptTemplate keeps literal JSON keys (not template vars).
_BASE_SYSTEM = (
    "你是资讯编辑。根据给定标题与正文片段，输出 JSON 对象："
    '{{"summary":"中文摘要","importance":整数}}。'
    "摘要要求：忠于原文、不编造、不夸大、保留核心事件，长度约 50～120 字。"
    "importance 为 1～10 的整数（9-10 重大行业事件，7-8 重要动态，5-6 一般，3-4 较低，1-2 很低）。"
    "只输出 JSON，不要其它文字。不要改写或输出分类。"
)

_FINANCE_EXTRA = (
    "本条为金融资讯：只陈述事实与信息摘要。"
    "禁止输出买入/卖出建议、股票推荐、投资建议、收益承诺或价格预测。"
)


@dataclass(frozen=True)
class SummarizeResult:
    summary: str | None
    importance: int
    ok: bool
    error: str | None = None


def _fallback(*, error: str) -> SummarizeResult:
    return SummarizeResult(summary=None, importance=5, ok=False, error=error)


def _parse_response(raw: str) -> SummarizeResult:
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_RE.search(text)
        if not match:
            return _fallback(error="invalid_json")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return _fallback(error="invalid_json")

    if not isinstance(data, dict):
        return _fallback(error="invalid_json_shape")

    summary_raw = data.get("summary")
    summary: str | None
    if isinstance(summary_raw, str) and summary_raw.strip():
        summary = summary_raw.strip()
    else:
        summary = None

    importance = 5
    imp_raw = data.get("importance")
    try:
        importance = int(imp_raw)
    except (TypeError, ValueError):
        importance = 5
    importance = max(1, min(10, importance))

    return SummarizeResult(summary=summary, importance=importance, ok=True)


def summarize_item(
    *,
    title: str,
    content: str | None,
    category: str,
) -> SummarizeResult:
    """LLM 摘要 + 重要性。失败时 importance=5、summary 可为 null。不改分类。"""
    if not llm_keys_ready():
        return _fallback(error="llm_not_configured")

    settings = get_settings()
    system = _BASE_SYSTEM
    if category == "finance":
        system = system + _FINANCE_EXTRA

    body = f"标题：{title}\n正文：{(content or '').strip() or '（无正文）'}"

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0,
            request_timeout=float(settings.news_llm_timeout),
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", system), ("human", "{text}")]
        )
        result = (prompt | model).invoke({"text": body})
        raw = str(result.content).strip()
    except Exception as exc:  # noqa: BLE001 — per-item isolation
        return _fallback(error=f"llm_error:{exc.__class__.__name__}")

    return _parse_response(raw)
