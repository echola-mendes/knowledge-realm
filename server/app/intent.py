from __future__ import annotations

import json
from typing import Literal

IntentLabel = Literal["knowledge", "plan", "booking", "chat"]

_INTENTS: tuple[str, ...] = ("knowledge", "plan", "booking", "chat")

_GREETINGS = ("你好", "您好", "hi", "hello", "在吗", "嗨", "哈喽", "早上好", "晚上好")
_PLAN_KEYWORDS = ("行程", "规划", "攻略", "出游", "旅游", "旅行", "机票", "航班", "酒店", "住宿")
_BOOKING_KEYWORDS = ("订", "预订", "预定了", "下单", "退订", "取消订单", "取消预订", "改签")


def _heuristic_intent(query: str) -> IntentLabel:
    """LLM 不可用时的兜底分类；只求不出错，不求精确。"""
    q = (query or "").strip().lower()
    if not q:
        return "chat"
    if len(q) <= 12 and any(g in q for g in _GREETINGS):
        return "chat"
    if any(k in q for k in _BOOKING_KEYWORDS) and any(k in q for k in ("机票", "酒店", "航班", "房间", "订单")):
        return "booking"
    if any(k in q for k in _PLAN_KEYWORDS):
        return "plan"
    return "knowledge"


def _llm_label(query: str, history_tail: list[dict[str, str]] | None = None) -> IntentLabel | None:
    """一次结构化 LLM 分类；任何失败返回 None，由启发式兜底。"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    history_text = "\n".join(
        f"{item.get('role')}: {str(item.get('content') or '')[:100]}" for item in (history_tail or [])[-4:]
    )
    try:
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
                    "你是意图分类器。只输出 JSON，格式："
                    '{"intent":"knowledge|plan|booking|chat"}。'
                    "knowledge=知识库问答/资料检索/报告生成；"
                    "plan=规划或调整出行方案（搜索比价、安排行程）；"
                    "booking=下单/取消/查询预订；"
                    "chat=寒暄或与知识库、出行无关的闲聊。",
                ),
                ("human", "最近对话：\n{history}\n\n用户消息：{query}"),
            ]
        )
        resp = (prompt | model).invoke({"history": history_text or "（无）", "query": query})
        raw = str(resp.content)
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if 0 <= start <= end else raw)
        if not isinstance(parsed, dict):
            return None
        label = str(parsed.get("intent") or "").strip()
        return label if label in _INTENTS else None
    except Exception:
        return None


def classify_intent(
    query: str,
    *,
    task: str = "agent",
    history_tail: list[dict[str, str]] | None = None,
) -> IntentLabel:
    """薄意图：只出标签，不做检索、不整合回答。task=report 强制走 knowledge。"""
    if task == "report":
        return "knowledge"
    label = _llm_label(query, history_tail)
    if label:
        return label
    return _heuristic_intent(query)
