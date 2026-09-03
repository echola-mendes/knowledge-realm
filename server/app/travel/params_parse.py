"""从中文口语句抽取出行参数（plan_agent 启发式兜底，不调用 LLM）。"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

_WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _weekday_on_week(ref: dt.date, weekday: int, week_offset: int) -> dt.date:
    """week_offset=0 本周，1 下周（周一为一周起点）。"""
    monday = ref - dt.timedelta(days=ref.weekday())
    return monday + dt.timedelta(weeks=week_offset, days=weekday)


def _nearest_future_weekday(ref: dt.date, weekday: int) -> dt.date:
    days = (weekday - ref.weekday()) % 7
    if days == 0:
        days = 7
    return ref + dt.timedelta(days=days)


def _parse_weekday_token(text: str, ref: dt.date) -> dt.date | None:
    if "明天" in text:
        return ref + dt.timedelta(days=1)
    if "后天" in text:
        return ref + dt.timedelta(days=2)
    m = re.search(r"下(?:周|星期)?([一二三四五六日天])", text)
    if m:
        return _weekday_on_week(ref, _WEEKDAY[m.group(1)], week_offset=1)
    m = re.search(r"(?:本|这)(?:周|星期)?([一二三四五六日天])", text)
    if m:
        wd = _WEEKDAY[m.group(1)]
        candidate = _weekday_on_week(ref, wd, week_offset=0)
        return candidate if candidate >= ref else _nearest_future_weekday(ref, wd)
    m = re.search(r"(?:周|星期)([一二三四五六日天])", text)
    if m:
        return _nearest_future_weekday(ref, _WEEKDAY[m.group(1)])
    return None


def _strip_leading_date(text: str) -> str:
    """去掉句首相对日期，避免「下周二上海出发」误把日期吃进城市名。"""
    stripped = text
    for pat in (
        r"^下(?:周|星期)?[一二三四五六日天]",
        r"^(?:本|这)(?:周|星期)?[一二三四五六日天]",
        r"^(?:周|星期)[一二三四五六日天]",
        r"^明天",
        r"^后天",
        r"^\d{4}-\d{2}-\d{2}",
    ):
        stripped = re.sub(pat, "", stripped, count=1)
    return stripped.lstrip("，, \t")


def _parse_cities(text: str) -> tuple[str | None, str | None]:
    cleaned = _strip_leading_date(text)
    city = r"([\u4e00-\u9fff]{2,6})"
    tail = r"(?:[，,。\s]|$|返回|经济|公务|头等|商务|舱)"
    patterns = (
        rf"{city}(?:市|省)?出发(?:去|到|至){city}{tail}",
        rf"从{city}(?:市|省)?(?:去|到|至|飞){city}{tail}",
        rf"{city}(?:市|省)?(?:去|到|飞){city}{tail}",
    )
    for pat in patterns:
        m = re.search(pat, cleaned)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return None, None


def _parse_return_date(text: str, ref: dt.date, depart: dt.date | None) -> dt.date | None:
    segment = text
    for part in re.split(r"[，,。]", text):
        if any(k in part for k in ("返回", "回程", "返程")):
            segment = part
            break
    m = re.search(r"([一二三四五六日天])(?:返回|回程|返程)", segment)
    if not m:
        return None
    wd = _WEEKDAY[m.group(1)]
    if depart:
        base_monday = depart - dt.timedelta(days=depart.weekday())
        candidate = base_monday + dt.timedelta(days=wd)
        if candidate <= depart:
            candidate += dt.timedelta(days=7)
        return candidate
    return _nearest_future_weekday(ref, wd)


_ROUTE_KEYWORDS = ("出发", "返回", "往返", "返程")


def _parse_destination_only(text: str) -> str | None:
    """「下周二去上海」类仅目的地口述。"""
    cleaned = _strip_leading_date(text)
    m = re.search(
        r"(?:去|到|至|飞)([\u4e00-\u9fff]{2,6})(?:[，,。\s]|$|返回|经济|公务|头等|商务|舱)",
        cleaned,
    )
    return m.group(1).strip() if m else None


def has_plan_oral_signal(text: str, ref: dt.date | None = None) -> bool:
    """正向机酒规划口述：城市(对) + 日期 + 出发/返回/往返（PRD §4.3 验收对齐）。"""
    raw = (text or "").strip()
    if not raw:
        return False
    params = parse_travel_params(raw, ref=ref)
    if not params.get("depart_date"):
        return False
    origin, dest = params.get("origin"), params.get("destination")
    if not dest:
        dest = _parse_destination_only(raw)
    if not dest:
        return False
    has_route = any(k in raw for k in _ROUTE_KEYWORDS) or bool(params.get("return_date"))
    if not has_route:
        return False
    # 城市对，或 PRD 口述「去上海 + 日期 + 返回」仅目的地
    return bool(origin and dest) or bool(dest)


def parse_travel_params(text: str, ref: dt.date | None = None) -> dict[str, Any]:
    """从单条用户消息抽取 origin/destination/depart_date/return_date/cabin。"""
    ref = ref or dt.date.today()
    raw = (text or "").strip()
    params: dict[str, Any] = {}

    iso = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if iso:
        params["depart_date"] = iso.group(1)

    origin, dest = _parse_cities(raw)
    if origin:
        params["origin"] = origin
    if dest:
        params["destination"] = dest

    cabin = re.search(r"(经济舱|公务舱|头等舱|商务舱)", raw)
    if cabin:
        params["cabin"] = cabin.group(1)

    depart: dt.date | None = None
    if params.get("depart_date"):
        try:
            depart = dt.date.fromisoformat(str(params["depart_date"]))
        except ValueError:
            depart = None
    if depart is None:
        # 出发日期：优先取句首/「出发」前的相对日期片段，避免和「周四返回」混淆
        head = raw.split("出发", 1)[0] if "出发" in raw else raw.split("返回", 1)[0]
        parsed = _parse_weekday_token(head, ref)
        if parsed:
            depart = parsed
            params["depart_date"] = parsed.isoformat()

    ret = _parse_return_date(raw, ref, depart)
    if ret:
        params["return_date"] = ret.isoformat()

    params["trip_type"] = infer_trip_type(raw, params)
    nights = nights_from_params(params)
    if nights is not None:
        params["nights"] = nights

    return params


TRIP_TYPES = ("business", "leisure", "study", "other")
TRIP_TYPE_LABELS = {
    "business": "商务出行",
    "leisure": "旅游度假",
    "study": "学习交流",
    "other": "其他",
}

_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("business", ("出差", "商务", "会议", "客户", "办公")),
    ("study", ("学习", "培训", "交流", "考试", "研修", "访学")),
    ("leisure", ("旅游", "度假", "玩", "蜜月", "亲子", "观光")),
)


def infer_trip_type(text: str, params: dict[str, Any] | None = None) -> str:
    """从已填字段或口语句识别行程类型；无法判断则为 other。无行程状态。"""
    raw_type = str((params or {}).get("trip_type") or "").strip()
    if raw_type in TRIP_TYPE_LABELS:
        return raw_type
    for key, label in TRIP_TYPE_LABELS.items():
        if raw_type == label:
            return key
    blob = f"{text or ''} {' '.join(str(v) for v in (params or {}).values() if v)}"
    for key, words in _TYPE_KEYWORDS:
        if any(w in blob for w in words):
            return key
    return "other"


def nights_from_params(params: dict[str, Any]) -> int | None:
    depart = params.get("depart_date")
    ret = params.get("return_date")
    if not depart or not ret:
        return None
    try:
        a = dt.date.fromisoformat(str(depart)[:10])
        b = dt.date.fromisoformat(str(ret)[:10])
    except ValueError:
        return None
    n = (b - a).days
    return n if n >= 0 else None
