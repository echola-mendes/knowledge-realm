"""TRAVEL-BOOK-1：预订子 Agent（HITL + 落库 + 限流）。

循环：reason（识别 list/book/cancel 并抽参数）→ run_tool → finalize。
写操作（book/cancel）在未获得 hitl_confirm 时只生成 pending_action，经 SSE
`type=hitl` 推送给前端；用户确认后同会话再次请求，confirmed 注入工具才落库。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BookingRecord
from app.travel import rate_limit

MAX_LOOPS = 6
WRITE_ACTIONS = ("book_flight", "book_hotel", "cancel")

_compiled = None


class BookingState(TypedDict, total=False):
    query: str
    messages: list[dict[str, str]]
    summary: str
    ltm_hits: list[dict[str, Any]]
    conversation_id: str | None
    user_id: str | None
    hitl_confirm: bool | None
    pending_action: dict[str, Any] | None
    params: dict[str, Any]
    next_action: Literal["list", "book_flight", "book_hotel", "cancel", "ask", "direct"]
    bookings: list[dict[str, Any]]
    tool_result: dict[str, Any] | None
    answer: str
    loop_count: int
    max_loops: int


def booking_initial_state(
    query: str,
    *,
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    ltm_hits: list[dict[str, Any]] | None = None,
    conversation_id: str | None = None,
    user_id: str | None = None,
    hitl_confirm: bool | None = None,
    pending_action: dict[str, Any] | None = None,
) -> BookingState:
    return {
        "query": query,
        "messages": list(history or []) + [{"role": "user", "content": query}],
        "summary": (summary or "").strip(),
        "ltm_hits": list(ltm_hits or []),
        "conversation_id": conversation_id,
        "user_id": str(user_id) if user_id else None,
        "hitl_confirm": hitl_confirm,
        "pending_action": pending_action,
        "params": {},
        "next_action": "direct",
        "bookings": [],
        "tool_result": None,
        "answer": "",
        "loop_count": 0,
        "max_loops": MAX_LOOPS,
    }


def _user_question(state: BookingState) -> str:
    for item in reversed(state.get("messages") or []):
        if item.get("role") == "user":
            return item.get("content") or ""
    return ""


def _emit(config: RunnableConfig, event: dict[str, Any]) -> None:
    emit = (config.get("configurable") or {}).get("emit")
    if callable(emit):
        try:
            emit(event)
        except Exception:
            pass



def _emit_booking_data(config: RunnableConfig, items: list[dict[str, Any]]) -> None:
    if items:
        _emit(config, {"type": "booking_data", "items": items})

def _reason_llm(state: BookingState) -> dict[str, Any] | None:
    """LLM 决策：提取动作与参数；可被测试替换。"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    history_text = "\n".join(
        f"{item.get('role')}: {str(item.get('content') or '')[:160]}"
        for item in (state.get("messages") or [])[-8:]
    )
    pending = state.get("pending_action")
    prompt_text = (
        "你是出行预订助手。只输出 JSON。\n"
        "动作：list=查询我的预订；book_flight=订机票；book_hotel=订酒店；"
        "cancel=取消预订；ask=信息不足询问；direct=与预订无关。\n"
        "参数：list 可不传；book_flight 需 flight_no/date/depart_date；"
        "book_hotel 需 hotel_name/check_in/check_out；cancel 需 booking_id。\n"
        f"当前会话是否有待确认动作：{'有' if pending else '无'}。"
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
                ("system", prompt_text),
                (
                    "human",
                    "历史对话：\n{history}\n\n当前消息：{question}\n\n已抽参数：{params}",
                ),
            ]
        )
        resp = (prompt | model).invoke(
            {
                "history": history_text or "（无）",
                "question": _user_question(state),
                "params": json.dumps(state.get("params") or {}, ensure_ascii=False),
            }
        )
        raw = str(resp.content)
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if 0 <= start <= end else raw)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception:
        return None


def reason_decide(state: BookingState) -> dict[str, Any]:
    """合并 LLM 输出，处理 hitl_confirm 与 pending_action。"""
    loop_count = int(state.get("loop_count") or 0) + 1
    pending = state.get("pending_action")
    hitl_confirm = state.get("hitl_confirm")

    # 用户拒绝：无论是否有 pending_action，直接取消
    if hitl_confirm is False:
        return {
            "loop_count": loop_count,
            "next_action": "direct",
            "pending_action": None,
            "answer": "已取消该操作。",
        }
    # 有待确认动作且用户确认：执行 pending_action
    if pending and hitl_confirm is True:
        return {
            "loop_count": loop_count,
            "next_action": pending.get("tool"),
            "params": dict(pending.get("args") or {}),
            "answer": "",
        }

    parsed = _reason_llm(state)
    if not isinstance(parsed, dict):
        # 无 LLM 时按关键词兜底
        parsed = _heuristic_decision(state)

    action = str(parsed.get("action") or "direct").strip()
    if action not in ("list", "book_flight", "book_hotel", "cancel", "ask", "direct"):
        action = "direct"

    old_params = dict(state.get("params") or {})
    new_params = parsed.get("params") or {}
    merged = {**old_params, **new_params}

    return {
        "loop_count": loop_count,
        "next_action": action,
        "params": merged,
        "answer": "",
    }


def _heuristic_decision(state: BookingState) -> dict[str, Any]:
    q = (_user_question(state) or state.get("query") or "").lower()
    if "预订" in q or "我的订单" in q or "订单" in q:
        if "取消" in q:
            return {"action": "cancel", "params": {}}
        return {"action": "list", "params": {}}
    if any(k in q for k in ("订机票", "预订机票", "买机票")):
        return {"action": "book_flight", "params": {}}
    if any(k in q for k in ("订酒店", "预订酒店", "订房间")):
        return {"action": "book_hotel", "params": {}}
    return {"action": "direct", "params": {}}


def node_reason(state: BookingState) -> dict[str, Any]:
    return reason_decide(state)


def route_after_reason(
    state: BookingState,
) -> Literal["run_tool", "ask", "finalize"]:
    return {
        "list": "run_tool",
        "book_flight": "run_tool",
        "book_hotel": "run_tool",
        "cancel": "run_tool",
        "ask": "ask",
        "direct": "finalize",
    }.get(state.get("next_action") or "direct", "finalize")


def _get_session(config: RunnableConfig) -> Session | None:
    session = (config.get("configurable") or {}).get("session")
    return session if isinstance(session, Session) else None


def _get_user_id(state: BookingState, config: RunnableConfig) -> uuid.UUID | None:
    raw = state.get("user_id") or (config.get("configurable") or {}).get("user_id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def list_bookings_tool(session: Session, user_id: uuid.UUID) -> dict[str, Any]:
    rows = session.scalars(
        select(BookingRecord)
        .where(BookingRecord.user_id == user_id)
        .order_by(BookingRecord.created_at.desc())
    ).all()
    return {
        "kind": "list",
        "items": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "vendor": row.vendor,
                "external_id": row.external_id,
                "status": row.status,
                "pay_url": row.pay_url,
                "payload": row.payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


def _vendor_book_flight(**kwargs: Any) -> dict[str, Any]:
    """供应商占位：真实环境接入 flyai/book-flight 等。"""
    return {
        "external_id": f"FLY-{uuid.uuid4().hex[:12].upper()}",
        "pay_url": "https://example.com/pay/flight",
    }


def _vendor_book_hotel(**kwargs: Any) -> dict[str, Any]:
    return {
        "external_id": f"HTL-{uuid.uuid4().hex[:12].upper()}",
        "pay_url": "https://example.com/pay/hotel",
    }


def _vendor_cancel(external_id: str | None) -> dict[str, Any]:
    return {"success": True, "external_id": external_id}


def book_flight_tool(
    session: Session,
    user_id: uuid.UUID,
    params: dict[str, Any],
    confirmed: bool | None,
) -> dict[str, Any]:
    flight_no = str(params.get("flight_no") or params.get("flightNo") or "")
    depart_date = str(params.get("date") or params.get("depart_date") or "")
    summary = f"预订机票 {flight_no}" + (f"（{depart_date}）" if depart_date else "")
    if not confirmed:
        return {
            "kind": "pending",
            "pending_action": {
                "tool": "book_flight",
                "args": {"flight_no": flight_no, "depart_date": depart_date},
                "summary": summary,
            },
        }
    rate_limit.check_write_rate(user_id)
    vendor_result = _vendor_book_flight(
        flight_no=flight_no,
        depart_date=depart_date,
        origin=params.get("origin"),
        destination=params.get("destination"),
    )
    record = BookingRecord(
        user_id=user_id,
        kind="flight",
        vendor="flyai",
        external_id=vendor_result.get("external_id"),
        payload={
            "flight_no": flight_no,
            "depart_date": depart_date,
            "origin": params.get("origin"),
            "destination": params.get("destination"),
        },
        status="pending",
        pay_url=vendor_result.get("pay_url"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return {
        "kind": "booked",
        "booking_id": str(record.id),
        "external_id": record.external_id,
        "pay_url": record.pay_url,
        "summary": summary,
    }


def book_hotel_tool(
    session: Session,
    user_id: uuid.UUID,
    params: dict[str, Any],
    confirmed: bool | None,
) -> dict[str, Any]:
    hotel_name = str(params.get("hotel_name") or params.get("hotelName") or "")
    check_in = str(params.get("check_in") or params.get("checkIn") or "")
    check_out = str(params.get("check_out") or params.get("checkOut") or "")
    summary = f"预订酒店 {hotel_name}" + (f"（{check_in} 至 {check_out}）" if check_in else "")
    if not confirmed:
        return {
            "kind": "pending",
            "pending_action": {
                "tool": "book_hotel",
                "args": {"hotel_name": hotel_name, "check_in": check_in, "check_out": check_out},
                "summary": summary,
            },
        }
    rate_limit.check_write_rate(user_id)
    vendor_result = _vendor_book_hotel(
        hotel_name=hotel_name, check_in=check_in, check_out=check_out
    )
    record = BookingRecord(
        user_id=user_id,
        kind="hotel",
        vendor="flyai",
        external_id=vendor_result.get("external_id"),
        payload={
            "hotel_name": hotel_name,
            "check_in": check_in,
            "check_out": check_out,
        },
        status="pending",
        pay_url=vendor_result.get("pay_url"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return {
        "kind": "booked",
        "booking_id": str(record.id),
        "external_id": record.external_id,
        "pay_url": record.pay_url,
        "summary": summary,
    }


def cancel_booking_tool(
    session: Session,
    user_id: uuid.UUID,
    params: dict[str, Any],
    confirmed: bool | None,
) -> dict[str, Any]:
    booking_id = str(params.get("booking_id") or params.get("id") or "")
    summary = f"取消预订 {booking_id[:8]}"
    if not confirmed:
        return {
            "kind": "pending",
            "pending_action": {
                "tool": "cancel",
                "args": {"booking_id": booking_id},
                "summary": summary,
            },
        }
    rate_limit.check_write_rate(user_id)
    try:
        bid = uuid.UUID(booking_id)
    except ValueError:
        return {"kind": "error", "message": "预订 ID 格式不正确"}
    record = session.get(BookingRecord, bid)
    if record is None or record.user_id != user_id:
        return {"kind": "error", "message": "未找到该预订"}
    _vendor_cancel(record.external_id)
    record.status = "cancelled"
    session.commit()
    session.refresh(record)
    return {"kind": "cancelled", "booking_id": str(record.id), "status": record.status}


def node_run_tool(state: BookingState, config: RunnableConfig) -> dict[str, Any]:
    session = _get_session(config)
    user_id = _get_user_id(state, config)
    action = state.get("next_action")
    params = dict(state.get("params") or {})
    confirmed = state.get("hitl_confirm")
    tool_result: dict[str, Any]

    if session is None or user_id is None:
        return {"tool_result": {"kind": "error", "message": "缺少会话或用户身份"}, "answer": "服务异常：无法获取用户信息。"}

    if action == "list":
        tool_result = list_bookings_tool(session, user_id)
    elif action == "book_flight":
        tool_result = book_flight_tool(session, user_id, params, confirmed)
    elif action == "book_hotel":
        tool_result = book_hotel_tool(session, user_id, params, confirmed)
    elif action == "cancel":
        tool_result = cancel_booking_tool(session, user_id, params, confirmed)
    else:
        tool_result = {"kind": "error", "message": "未知动作"}

    updates: dict[str, Any] = {"tool_result": tool_result}
    if tool_result.get("kind") == "pending":
        pending = tool_result["pending_action"]
        pending["confirmed"] = None
        updates["pending_action"] = pending
        _emit(config, {"type": "hitl", **pending})
        updates["answer"] = f"请确认是否{pending['summary']}？"
    elif tool_result.get("kind") == "list":
        items = tool_result.get("items") or []
        _emit_booking_data(config, items)
        updates["bookings"] = items
    elif tool_result.get("kind") == "booked":
        item = {
            "id": tool_result.get("booking_id"),
            "kind": "flight" if action == "book_flight" else "hotel",
            "external_id": tool_result.get("external_id"),
            "status": "pending",
            "pay_url": tool_result.get("pay_url"),
        }
        _emit_booking_data(config, [item])
        updates["bookings"] = [item]
    return updates


def node_ask(state: BookingState) -> dict[str, Any]:
    missing: list[str] = []
    action = state.get("next_action")
    params = state.get("params") or {}
    if action in ("book_flight", "book_hotel", "cancel"):
        if not params.get("flight_no") and not params.get("hotel_name") and not params.get("booking_id"):
            missing.append("具体预订信息")
    text = "为完成预订操作，请补充：" + "、".join(missing or ["必要信息"]) + "。"
    return {"answer": text}


def node_finalize(state: BookingState) -> dict[str, Any]:
    tool_result = state.get("tool_result")
    pending = state.get("pending_action")
    bookings = list(state.get("bookings") or [])

    def _with_bookings(payload: dict[str, Any]) -> dict[str, Any]:
        if bookings:
            payload["bookings"] = bookings
        return payload

    # 已经由 run_tool 生成 pending answer
    if state.get("answer"):
        return _with_bookings({"answer": state["answer"], "pending_action": pending})

    if tool_result is None:
        return _with_bookings({"answer": "我可以帮您查询或管理预订，请告诉我具体需求。"})

    kind = tool_result.get("kind")
    if kind == "list":
        items = tool_result.get("items") or []
        if not items:
            return _with_bookings({"answer": "您当前没有预订记录。"})
        lines = []
        for item in items:
            lines.append(
                f"- [{item['kind']}] {item['external_id'] or item['id'][:8]} "
                f"状态：{item['status']}"
            )
        return _with_bookings({"answer": "您的预订：\n" + "\n".join(lines), "bookings": items})
    if kind == "booked":
        pay = tool_result.get("pay_url")
        booked_items = bookings or [
            {
                "id": tool_result.get("booking_id"),
                "kind": "flight",
                "external_id": tool_result.get("external_id"),
                "status": "pending",
                "pay_url": pay,
            }
        ]
        return _with_bookings(
            {
                "answer": (
                    f"预订已提交：{tool_result['summary']}，"
                    f"订单号 {tool_result['booking_id'][:8]}"
                    f"{('，支付链接：' + pay) if pay else ''}。"
                ),
                "bookings": booked_items,
            }
        )
    if kind == "cancelled":
        return _with_bookings({"answer": f"预订 {tool_result['booking_id'][:8]} 已取消。"})
    if kind == "error":
        return _with_bookings({"answer": f"操作失败：{tool_result.get('message')}"})

    return _with_bookings({"answer": "预订助手已处理您的请求。"})


def build_booking_graph():
    global _compiled
    if _compiled is not None:
        return _compiled
    graph = StateGraph(BookingState)
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
    graph.add_edge("run_tool", "finalize")
    graph.add_edge("ask", END)
    graph.add_edge("finalize", END)
    _compiled = graph.compile()
    return _compiled


def reset_booking_graph() -> None:
    global _compiled
    _compiled = None
