"""确认方案 → 从 plan_record 抽出可预订航班参数。"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlanRecord

# 确认方案1 / 确认P1 / 选方案 2 / 要方案1 / 方案1确认
_CONFIRM_PLAN_RE = re.compile(
    r"(?:"
    r"(?:确认|选择|选|要)\s*(?:方案|P|p)\s*(\d+)"
    r"|"
    r"(?:方案|P|p)\s*(\d+)\s*(?:确认|可以|就它|就这个)"
    r")"
)


def is_confirm_plan_query(query: str) -> bool:
    return parse_confirm_option_index(query) is not None


def parse_confirm_option_index(query: str) -> int | None:
    q = (query or "").strip()
    if not q:
        return None
    m = _CONFIRM_PLAN_RE.search(q)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        idx = int(raw)
    except ValueError:
        return None
    return idx if idx >= 1 else None


def load_latest_plan_record(
    session: Session,
    user_id: uuid.UUID,
    *,
    conversation_id: str | uuid.UUID | None = None,
) -> PlanRecord | None:
    stmt = select(PlanRecord).where(PlanRecord.user_id == user_id)
    cid: uuid.UUID | None = None
    if conversation_id:
        try:
            cid = uuid.UUID(str(conversation_id))
        except ValueError:
            cid = None
    if cid is not None:
        stmt = stmt.where(PlanRecord.conversation_id == cid)
    stmt = stmt.order_by(PlanRecord.created_at.desc()).limit(1)
    return session.scalars(stmt).first()


def resolve_option(plan_payload: dict[str, Any] | None, index: int) -> dict[str, Any] | None:
    options = (plan_payload or {}).get("options")
    if not isinstance(options, list) or not options:
        return None
    wanted = f"opt-{index}"
    for opt in options:
        if isinstance(opt, dict) and str(opt.get("id") or "") == wanted:
            return opt
    if 1 <= index <= len(options):
        opt = options[index - 1]
        return opt if isinstance(opt, dict) else None
    return None


def _seg_flight_no(seg: dict[str, Any]) -> str:
    return str(
        seg.get("flight_no")
        or seg.get("flightNo")
        or seg.get("marketingTransportNo")
        or ""
    ).strip()


def booking_params_from_option(
    option: dict[str, Any],
    *,
    plan_record: PlanRecord | None = None,
    plan_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """从方案 option 抽出 book_flight 参数；无航班号则返回 None。"""
    segments = [s for s in (option.get("segments") or []) if isinstance(s, dict)]
    flight_segs = [s for s in segments if str(s.get("type") or "flight") == "flight"]
    if not flight_segs:
        flight_segs = segments
    if not flight_segs:
        return None

    outbound = next((s for s in flight_segs if s.get("leg") in ("outbound", "out", "去程")), flight_segs[0])
    ret = next((s for s in flight_segs if s.get("leg") in ("return", "inbound", "返程")), None)
    if ret is None and len(flight_segs) >= 2:
        ret = flight_segs[1]

    out_no = _seg_flight_no(outbound)
    if not out_no:
        # summary 首 token 兜底（如 "ZH9101 SZX→PEK …"）
        summary = str(outbound.get("summary") or "").strip()
        out_no = summary.split()[0] if summary else ""
    if not out_no:
        return None

    payload = plan_payload if isinstance(plan_payload, dict) else {}
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    depart_date = (
        str(params.get("depart_date") or params.get("dep_date") or "").strip()
        or (str(plan_record.depart_date) if plan_record and plan_record.depart_date else "")
    )
    return_date = str(params.get("return_date") or params.get("ret_date") or "").strip()
    origin = (
        str(outbound.get("dep_place") or params.get("origin") or "").strip()
        or (str(plan_record.origin) if plan_record and plan_record.origin else "")
    )
    destination = (
        str(outbound.get("arr_place") or params.get("destination") or "").strip()
        or (str(plan_record.destination) if plan_record and plan_record.destination else "")
    )

    ret_no = ""
    if ret is not None:
        ret_no = _seg_flight_no(ret)
        if not ret_no:
            summary = str(ret.get("summary") or "").strip()
            ret_no = summary.split()[0] if summary else ""

    option_id = str(option.get("id") or "")
    label = str(option.get("label") or option_id or "所选方案")
    bits = [f"去程 {out_no}" + (f"（{depart_date}）" if depart_date else "")]
    if ret_no:
        bits.append(f"返程 {ret_no}" + (f"（{return_date}）" if return_date else ""))

    out: dict[str, Any] = {
        "flight_no": out_no,
        "depart_date": depart_date,
        "origin": origin,
        "destination": destination,
        "option_id": option_id,
        "option_label": label,
        "segments_summary": "；".join(bits),
    }
    if ret_no:
        out["return_flight_no"] = ret_no
        out["return_date"] = return_date
    return out


def resolve_confirm_booking_params(
    session: Session,
    user_id: uuid.UUID,
    query: str,
    *,
    conversation_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    """解析确认方案请求。

    返回：
    - ok + params：可发起 book_flight
    - error + message：无法解析/无方案
    """
    index = parse_confirm_option_index(query)
    if index is None:
        return {"ok": False, "message": "未识别方案编号"}

    record = load_latest_plan_record(session, user_id, conversation_id=conversation_id)
    if record is None and conversation_id:
        # 同会话无记录时回退到用户最近一次方案
        record = load_latest_plan_record(session, user_id, conversation_id=None)
    if record is None:
        return {"ok": False, "message": "未找到可确认的行程方案，请先规划行程后再确认。"}

    payload = record.payload if isinstance(record.payload, dict) else {}
    option = resolve_option(payload, index)
    if option is None:
        count = len(payload.get("options") or []) if isinstance(payload.get("options"), list) else 0
        if count == 0:
            return {
                "ok": False,
                "message": "当前方案缺少可预订明细，请重新生成行程方案后再确认。",
            }
        return {"ok": False, "message": f"没有方案{index}，当前共 {count} 套方案。"}

    params = booking_params_from_option(option, plan_record=record, plan_payload=payload)
    if not params:
        return {"ok": False, "message": f"方案{index}缺少航班号，无法进入预订。"}
    return {"ok": True, "params": params, "option_index": index}
