from __future__ import annotations

import json
from typing import Literal

from app.travel.params_parse import has_plan_oral_signal

IntentLabel = Literal["knowledge", "plan", "booking", "chat"]

_INTENTS: tuple[str, ...] = ("knowledge", "plan", "booking", "chat")

_GREETINGS = ("你好", "您好", "hi", "hello", "在吗", "嗨", "哈喽", "早上好", "晚上好")
# 明确规划/机酒词；城市+日期+路线走 has_plan_oral_signal，舱位+路线纠偏走 _strong_travel
_PLAN_KEYWORDS = ("行程", "规划", "攻略", "出游", "旅游", "旅行", "机票", "航班", "酒店", "住宿")
_CABIN_KEYWORDS = ("经济舱", "公务舱", "头等舱", "商务舱")
_ROUTE_KEYWORDS = ("出发", "返回", "往返", "返程")
_BOOKING_KEYWORDS = ("订", "预订", "预定了", "下单", "退订", "取消订单", "取消预订", "改签")

# LLM 判错时可被规则纠正为 plan 的标签
_MISJUDGED_TO_PLAN = frozenset({None, "knowledge", "chat"})


def _strong_travel(query: str) -> bool:
    """纠偏信号：舱位 + 出发/返回（航空口语，即使无完整城市/date 也防 knowledge 编造）。"""
    q = (query or "").strip()
    has_cabin = any(k in q for k in _CABIN_KEYWORDS)
    has_route = any(k in q for k in _ROUTE_KEYWORDS)
    return has_cabin and has_route


def _heuristic_intent(query: str) -> IntentLabel:
    """LLM 不可用时的兜底分类；只求不出错，不求精确。"""
    q = (query or "").strip().lower()
    if not q:
        return "chat"
    if len(q) <= 12 and any(g in q for g in _GREETINGS):
        return "chat"
    if any(k in q for k in _BOOKING_KEYWORDS) and any(k in q for k in ("机票", "酒店", "航班", "房间", "订单")):
        return "booking"
    if has_plan_oral_signal(query) or _strong_travel(query):
        return "plan"
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
                    "plan=机酒出行规划（搜索比价、安排行程；含城市+日期+往返/出发/返回口述）；"
                    "booking=下单/取消/查询预订；"
                    "chat=寒暄或与知识库、出行无关的闲聊。"
                    "用户给出出发地/目的地/日期并要求出行安排时必须是 plan，禁止当成 knowledge 直接编航班。",
                ),
                ("human", "最近对话：\n{history}\n\n用户消息：{query}"),
            ]
        )
        resp = (prompt | model).invoke({"history": history_text or "（无）", "query": query})
        raw = str(resp.content)
        think_end = raw.rfind("</think>")
        if think_end != -1:
            raw = raw[think_end + len("</think>") :]
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if 0 <= start <= end else raw)
        if not isinstance(parsed, dict):
            return None
        label = str(parsed.get("intent") or "").strip()
        return label if label in _INTENTS else None
    except Exception:
        return None


def _rule_correct_to_plan(query: str, llm_label: IntentLabel | None) -> bool:
    """LLM 判成 knowledge/chat（或失败）时，用正向/纠偏规则改走 plan。"""
    if llm_label not in _MISJUDGED_TO_PLAN:
        return False
    if has_plan_oral_signal(query):
        return True
    if _strong_travel(query):
        return True
    return False


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
    if _rule_correct_to_plan(query, label):
        return "plan"
    if label:
        return label
    return _heuristic_intent(query)
