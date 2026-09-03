"""itinerary_plan_agent：行程规划子 Agent（TRAVEL-PLAN-1）。

循环：reason（抽取参数并决策）→ run_tool（flights/hotels/plan/save）→ reason …
- 缺少必要要素（出发地/目的地/出发日期）时 reason 输出 ask + need_fields，由本 Agent 对话补问；
- 口头偏好改方案：每轮从对话历史重抽参数，未提及的日期/城市沿用上一轮（params merge），不丢要素；
- 无 checkpointer：多轮补问靠 DB 消息历史（STM）与本图每轮重入。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.travel import tools as travel_tools
from app.travel.params_parse import infer_trip_type, nights_from_params

MAX_LOOPS = 6
REQUIRED_FIELDS = ("origin", "destination", "depart_date")

FIELD_LABELS = {
    "origin": "出发地",
    "destination": "目的地",
    "depart_date": "出发日期",
    "return_date": "返程日期",
    "cabin": "舱位偏好",
    "budget": "预算",
    "check_in_date": "入住日期",
    "check_out_date": "离店日期",
}

_compiled = None


class PlanState(TypedDict, total=False):
    query: str
    messages: list[dict[str, str]]
    summary: str
    ltm_hits: list[dict[str, Any]]
    conversation_id: str | None
    user_id: str | None
    params: dict[str, Any]
    need_fields: list[str]
    next_action: Literal["flights", "hotels", "plan", "save", "ask", "direct"]
    flights_raw: dict[str, Any] | None
    hotels_raw: dict[str, Any] | None
    plan: dict[str, Any]
    plan_html: dict[str, Any]
    travel_data: dict[str, Any]
    progress: list[str]
    answer: str
    loop_count: int
    max_loops: int


def plan_initial_state(
    query: str,
    *,
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    ltm_hits: list[dict[str, Any]] | None = None,
    conversation_id: str | None = None,
    user_id: str | None = None,
) -> PlanState:
    return {
        "query": query,
        "messages": list(history or []) + [{"role": "user", "content": query}],
        "summary": (summary or "").strip(),
        "ltm_hits": list(ltm_hits or []),
        "conversation_id": conversation_id,
        "user_id": str(user_id) if user_id else None,
        "params": {},
        "need_fields": [],
        "next_action": "direct",
        "flights_raw": None,
        "hotels_raw": None,
        "travel_data": {},
        "progress": [],
        "answer": "",
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
    }


def _emit(config: RunnableConfig, event: dict[str, Any]) -> None:
    emit = (config.get("configurable") or {}).get("emit")
    if callable(emit):
        try:
            emit(event)
        except Exception:
            pass


def _emit_progress(config: RunnableConfig, text: str, progress: list[str]) -> None:
    _emit(config, {"type": "progress", "text": text})
    return None



def _get_session(config: RunnableConfig):
    from sqlalchemy.orm import Session

    session = (config.get("configurable") or {}).get("session")
    return session if isinstance(session, Session) else None


def _get_user_id(state: PlanState, config: RunnableConfig) -> uuid.UUID | None:
    raw = state.get("user_id") or (config.get("configurable") or {}).get("user_id")
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _parse_conversation_id(raw: str | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _plan_title(params: dict[str, Any]) -> str:
    origin = (params.get("origin") or "").strip()
    destination = (params.get("destination") or "").strip()
    if origin and destination:
        return f"{origin}→{destination}"[:200]
    if destination:
        return f"前往{destination}"[:200]
    return "行程方案"


def persist_plan_record(
    session,
    user_id: uuid.UUID,
    *,
    conversation_id: str | None,
    params: dict[str, Any],
    plan: dict[str, Any],
    plan_html: dict[str, Any],
):
    """方案页生成后落库；无 MinIO 也写（url/key 可空）。失败静默，不影响 SSE。"""
    params = params or {}
    try:
        from app.models import PlanRecord

        record = PlanRecord(
            user_id=user_id,
            conversation_id=_parse_conversation_id(conversation_id),
            title=_plan_title(params),
            origin=(params.get("origin") or None),
            destination=(params.get("destination") or None),
            depart_date=(params.get("depart_date") or params.get("dep_date") or None),
            trip_type=infer_trip_type("", params),
            nights=nights_from_params(params),
            minio_key=(plan_html or {}).get("key"),
            url=(plan_html or {}).get("url"),
            payload={
                "recommendation": (plan or {}).get("recommendation"),
                "total_price_summary": (plan or {}).get("total_price_summary"),
                "option_count": len((plan or {}).get("options") or []),
                "options": (plan or {}).get("options") or [],
                "params": params,
            },
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return None

def _user_question(state: PlanState) -> str:
    for item in reversed(state.get("messages") or []):
        if item.get("role") == "user":
            return item.get("content") or ""
    return ""


def _reason_llm(state: PlanState) -> dict[str, Any] | None:
    """LLM 决策：抽取/更新参数并给出动作。可被测试替换；失败返回 None。"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    history_text = "\n".join(
        f"{item.get('role')}: {str(item.get('content') or '')[:160]}"
        for item in (state.get("messages") or [])[-8:]
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
                    "你是出行规划调度器。只输出 JSON。"
                    '从对话抽取出行参数：{"params":{"origin","destination","depart_date","return_date",'
                    '"cabin","adults","budget","poi_name","hotel_stars","max_price",'
                    '"trip_type":"business|leisure|study|other"},'
                    '"action":"flights|hotels|plan|save|ask|direct"}。'
                    "日期格式 YYYY-MM-DD。trip_type：出差会议=business，旅游度假=leisure，学习交流=study，否则 other。"
                    "只写本轮新提及或更正的字段，未提及的字段不要输出（保留旧值由系统合并）。"
                    "动作规则：要素齐全先查机票（flights）；需要酒店且已启用再 hotels；"
                    "已有搜索结果则 plan 生成方案；方案生成后 save 保存方案页；"
                    "要素缺失（出发地/目的地/出发日期）选 ask；与出行无关选 direct。",
                ),
                (
                    "human",
                    "历史对话：\n{history}\n\n当前用户消息：{question}\n\n已抽参数：{params}\n"
                    "已有结果：flights={has_flights} hotels={has_hotels} plan={has_plan} saved={saved}",
                ),
            ]
        )
        has_flights = bool((state.get("flights_raw") or {}).get("itemList"))
        resp = (
            prompt
            | model
        ).invoke(
            {
                "history": history_text or "（无）",
                "question": _user_question(state),
                "params": json.dumps(state.get("params") or {}, ensure_ascii=False),
                "has_flights": has_flights,
                "has_hotels": bool(state.get("hotels_raw")),
                "has_plan": bool(state.get("plan")),
                "saved": bool(state.get("plan_html")),
            }
        )
        raw = str(resp.content)
        think_end = raw.rfind("</think>")
        if think_end != -1:
            raw = raw[think_end + len("</think>") :]
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if 0 <= start <= end else raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _heuristic_params(state: PlanState) -> dict[str, Any]:
    """从当前用户消息做规则抽取，补 LLM 漏掉的口语字段（城市/相对日期/舱位）。"""
    from app.travel.params_parse import parse_travel_params

    return parse_travel_params(_user_question(state))


def reason_decide(state: PlanState) -> dict[str, Any]:
    """纯决策函数（无副作用），返回 state 更新。"""
    parsed = _reason_llm(state)
    params_update: dict[str, Any] = {}
    action = ""
    if parsed:
        action = str(parsed.get("action") or "")
        raw_params = parsed.get("params")
        if isinstance(raw_params, dict):
            params_update = {k: v for k, v in raw_params.items() if v not in (None, "")}
    merged = dict(state.get("params") or {})
    merged.update(_heuristic_params(state))
    merged.update(params_update)
    missing = [f for f in REQUIRED_FIELDS if not merged.get(f)]
    flights_raw = state.get("flights_raw")
    flights_searched = flights_raw is not None
    has_flight_results = bool((flights_raw or {}).get("itemList"))
    # 硬规则：要素缺失必补问，优先于 LLM 动作（已搜过票则不再 ask）
    if missing and not flights_searched:
        return {"params": merged, "need_fields": missing, "next_action": "ask"}
    # 启发式已补齐要素时，忽略 LLM 误判的 ask
    if not missing and action == "ask":
        action = ""
    if not parsed or not action:
        # 无 LLM 或无效动作：要素齐则按既定顺序走，避免空转
        if not flights_searched:
            action = "flights"
        elif not has_flight_results:
            action = "direct"
        elif not state.get("plan"):
            action = "plan"
        elif not state.get("plan_html"):
            action = "save"
        else:
            action = "direct"
    if action == "flights" and flights_searched:
        action = "plan" if has_flight_results else "direct"
    # 已搜过且无票：禁止继续 plan/save/hotels（否则空方案页）
    if flights_searched and not has_flight_results and action in ("plan", "save", "hotels"):
        action = "direct"
    if action == "plan" and not flights_searched:
        action = "flights"
    if action == "save" and not state.get("plan"):
        action = "plan"
    if action not in ("flights", "hotels", "plan", "save", "ask", "direct"):
        action = "plan" if has_flight_results else ("flights" if not flights_searched else "direct")
    return {"params": merged, "need_fields": [], "next_action": action}


def node_reason(state: PlanState) -> dict[str, Any]:
    if int(state.get("loop_count") or 0) >= int(state.get("max_loops") or MAX_LOOPS):
        return {"next_action": "direct"}
    updates = reason_decide(state)
    if updates.get("next_action") in ("flights", "hotels", "plan", "save") and int(
        state.get("loop_count") or 0
    ) + 1 > int(state.get("max_loops") or MAX_LOOPS):
        return {"next_action": "direct"}
    return updates


def route_after_reason(state: PlanState) -> Literal["run_tool", "ask", "finalize"]:
    action = state.get("next_action")
    if action == "ask":
        return "ask"
    if action in ("flights", "hotels", "plan", "save"):
        return "run_tool"
    return "finalize"


def node_run_tool(state: PlanState, config: RunnableConfig) -> dict[str, Any]:
    loop_count = int(state.get("loop_count") or 0) + 1
    action = state.get("next_action")
    progress = list(state.get("progress") or [])
    params = dict(state.get("params") or {})
    updates: dict[str, Any] = {"loop_count": loop_count}

    if action == "flights":
        progress.append("正在搜索机票…")
        _emit_progress(config, progress[-1], progress)
        raw = travel_tools.search_flights_tool(params)
        count = len(raw.get("itemList") or []) if isinstance(raw.get("itemList"), list) else 0
        if raw.get("kind") == "error":
            progress.append(f"机票搜索失败：{raw.get('message')}")
            _emit_progress(config, progress[-1], progress)
        else:
            progress.append(f"机票搜索完成（{count} 条）")
            _emit_progress(config, progress[-1], progress)
            if raw.get("roundtripFallback") == "one_way":
                progress.append(str(raw.get("systemMessage") or "往返无结果，已改为单程去程。"))
                _emit_progress(config, progress[-1], progress)
        travel_data = dict(state.get("travel_data") or {})
        from app.travel.tools import _dedupe_flight_items

        item_list = raw.get("itemList") if raw.get("kind") != "error" else raw
        if isinstance(item_list, list):
            travel_data["flights"] = _dedupe_flight_items([i for i in item_list if isinstance(i, dict)])
        else:
            travel_data["flights"] = item_list
        _emit(config, {"type": "travel_data", **travel_data})
        updates.update({"flights_raw": raw, "travel_data": travel_data, "progress": progress})
        return updates

    if action == "hotels":
        progress.append("正在搜索酒店…")
        _emit_progress(config, progress[-1], progress)
        raw = travel_tools.search_hotels_tool(params)
        if raw.get("kind") == "placeholder":
            progress.append("酒店源未配置，跳过酒店（不伪造房型）")
        elif raw.get("kind") == "error":
            progress.append(f"酒店搜索失败：{raw.get('message')}")
        else:
            progress.append("酒店搜索完成")
        _emit_progress(config, progress[-1], progress)
        travel_data = dict(state.get("travel_data") or {})
        travel_data["hotels"] = raw
        _emit(config, {"type": "travel_data", **travel_data})
        updates.update({"hotels_raw": raw, "travel_data": travel_data, "progress": progress})
        return updates

    if action == "plan":
        progress.append("正在生成可对比方案…")
        _emit_progress(config, progress[-1], progress)
        plan = travel_tools.plan_itinerary(
            state.get("flights_raw"), state.get("hotels_raw"), params
        )
        progress.append("方案生成完成")
        _emit_progress(config, progress[-1], progress)
        travel_data = dict(state.get("travel_data") or {})
        travel_data["plan"] = plan
        _emit(config, {"type": "travel_data", **travel_data})
        updates.update({"plan": plan, "travel_data": travel_data, "progress": progress})
        return updates

    if action == "save":
        progress.append("正在生成方案页…")
        _emit_progress(config, progress[-1], progress)
        plan_html = travel_tools.save_plan_html(
            state.get("plan") or {},
            state.get("flights_raw"),
            state.get("hotels_raw"),
            params,
            state.get("conversation_id"),
        )
        session = _get_session(config)
        user_id = _get_user_id(state, config)
        if session is not None and user_id is not None:
            record = persist_plan_record(
                session,
                user_id,
                conversation_id=state.get("conversation_id"),
                params=params,
                plan=state.get("plan") or {},
                plan_html=plan_html,
            )
            if record is not None:
                plan_html = {**plan_html, "plan_id": str(record.id)}
        progress.append(plan_html.get("note") or "方案页已生成")
        _emit_progress(config, progress[-1], progress)
        _emit(config, {"type": "plan_html", **plan_html})
        updates.update({"plan_html": plan_html, "progress": progress})
        return updates

    return updates


def node_ask(state: PlanState) -> dict[str, Any]:
    labels = [FIELD_LABELS.get(f, f) for f in (state.get("need_fields") or list(REQUIRED_FIELDS))]
    answer = "为给出可比方案，请补充以下信息：" + "、".join(labels) + "。"
    return {"answer": answer}


def _fallback_plan_answer(state: PlanState, *, flights_count: int) -> str:
    """LLM 不可用时用已生成方案拼一段可读总结，避免整次请求 500。"""
    params = dict(state.get("params") or {})
    plan = state.get("plan") or {}
    route = "→".join(p for p in (params.get("origin"), params.get("destination")) if p)
    date_bits = [params.get("depart_date"), params.get("return_date"), params.get("cabin")]
    head = "已根据你的出行条件生成方案"
    extras = "，".join(x for x in (route, *[str(b) for b in date_bits if b]) if x)
    if extras:
        head += f"（{extras}）"
    lines = [head + "。"]
    if flights_count:
        lines.append(f"共搜到 {flights_count} 条航班。")
    rec = plan.get("recommendation") if isinstance(plan.get("recommendation"), dict) else {}
    if rec:
        rec_id = rec.get("option_id") or ""
        reason = rec.get("reason") or ""
        rec_line = "推荐" + (f" {rec_id}" if rec_id else "")
        if reason:
            rec_line += f"：{reason}"
        lines.append(rec_line + "。")
    price = plan.get("total_price_summary")
    if price:
        lines.append(f"总价：{price}。")
    note = (state.get("plan_html") or {}).get("note")
    if note:
        lines.append(str(note))
    return "\n".join(lines)


def _plan_confirmation_answer(state: PlanState) -> str | None:
    """方案页已生成时，聊天区只给短确认（对齐 html-plan skill）。"""
    plan_html = state.get("plan_html") or {}
    if not plan_html.get("html"):
        return None
    note = str(plan_html.get("note") or "").strip()
    base = "方案已生成，请查看下方完整方案展示。"
    return f"{base}{note}" if note else base


def node_finalize(state: PlanState) -> dict[str, Any]:
    from app import llm as llm_mod

    params = dict(state.get("params") or {})
    plan = state.get("plan") or {}
    flights = state.get("flights_raw") or {}
    count = len(flights.get("itemList") or []) if isinstance(flights.get("itemList"), list) else 0
    if not plan and not count:
        if flights.get("kind") == "error":
            return {"answer": f"暂未能生成行程方案：{flights.get('message')}"}
        if state.get("flights_raw") is not None:
            hint = str(flights.get("systemMessage") or "").strip()
            msg = "暂未能生成行程方案：未搜到符合条件的航班，请调整日期或舱位后重试。"
            if hint:
                msg += f" {hint}"
            return {"answer": msg}
        return {"answer": "暂未能生成行程方案：请补充出行要素（出发地、目的地、出发日期）后重试。"}

    short = _plan_confirmation_answer(state)
    if short:
        return {"answer": short}

    context = json.dumps(
        {
            "params": params,
            "plan": plan,
            "flights_count": count,
            "plan_page": (state.get("plan_html") or {}).get("note"),
        },
        ensure_ascii=False,
    )
    history = [
        (str(m.get("role") or ""), str(m.get("content") or ""))
        for m in (state.get("messages") or [])[:-1]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    try:
        answer = llm_mod.chat(
            "请用一两句话告知用户方案已准备好，引导其查看下方方案卡片；禁止输出航班明细、支付链接、退改签/行李规则、体验模式说明或长篇行程概览。",
            context,
            history,
            summary=(state.get("summary") or "").strip() or None,
            ltm=state.get("ltm_hits") or None,
        )
    except Exception:
        answer = _fallback_plan_answer(state, flights_count=count)
    return {"answer": answer}


def build_plan_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    graph = StateGraph(PlanState)
    graph.add_node("reason", node_reason)
    graph.add_node("run_tool", node_run_tool)
    graph.add_node("ask", node_ask)
    graph.add_node("finalize", node_finalize)
    graph.add_edge(START, "reason")
    graph.add_conditional_edges(
        "reason",
        route_after_reason,
        {"run_tool": "run_tool", "ask": "ask", "finalize": "finalize"},
    )
    graph.add_edge("run_tool", "reason")
    graph.add_edge("ask", END)
    graph.add_edge("finalize", END)
    _compiled = graph.compile()
    return _compiled


def reset_plan_graph() -> None:
    global _compiled
    _compiled = None
