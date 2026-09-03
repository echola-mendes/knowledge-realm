"""出发地 / 目的地天气（wttr.in，无需 API Key）。失败降级为空，不阻断方案页。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

import httpx

WTTR_BASE = "https://wttr.in/"
TIMEOUT_SECONDS = 8.0
WET_KEYWORDS = ("雨", "雪", "rain", "snow", "drizzle", "shower", "sleet")
SEVERE_KEYWORDS = ("暴", "雾", "霾", "雷", "大风", "storm", "fog", "thunder", "gale", "typhoon")


def fetch_city_weather(city: str, date: str | None = None) -> dict[str, Any] | None:
    """查询单城天气。返回 city/description/min_temp/max_temp/date/hint；失败返回 None。"""
    name = (city or "").strip()
    if not name:
        return None
    try:
        resp = httpx.get(
            WTTR_BASE + quote(name),
            params={"format": "j1", "lang": "zh"},
            headers={"User-Agent": "curl/8.0", "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    day = _pick_day(raw, date)
    description = _description(raw, day)
    min_temp, max_temp = _temps(raw, day)
    if not description and min_temp is None and max_temp is None:
        return None
    used_date = (day or {}).get("date") if day else date
    return {
        "city": name,
        "date": used_date,
        "description": description or "—",
        "min_temp": min_temp,
        "max_temp": max_temp,
        "hint": _city_hint(description),
        "beyond_range": bool(date and used_date and date != used_date),
    }


def fetch_trip_weather(
    origin: str | None,
    destination: str | None,
    depart_date: str | None = None,
    return_date: str | None = None,
) -> dict[str, Any]:
    """并行查询出发地、目的地天气，并生成出行建议。"""
    origin_name = (origin or "").strip()
    dest_name = (destination or "").strip()
    origin_w: dict[str, Any] | None = None
    dest_w: dict[str, Any] | None = None
    jobs: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        if origin_name:
            jobs["origin"] = pool.submit(fetch_city_weather, origin_name, depart_date)
        if dest_name and dest_name != origin_name:
            jobs["destination"] = pool.submit(fetch_city_weather, dest_name, depart_date)
        elif dest_name and dest_name == origin_name:
            jobs["same"] = True
        origin_w = jobs["origin"].result() if "origin" in jobs else None
        dest_w = origin_w if jobs.get("same") else (
            jobs["destination"].result() if "destination" in jobs else None
        )
    return {
        "origin": origin_w,
        "destination": dest_w,
        "advice": _trip_advice(origin_w, dest_w),
    }


def format_weather_item(item: dict[str, Any] | None, role: str) -> str:
    """方案页单城文案，如「上海 多云，28-35°C，适合出行」。"""
    if not item:
        return ""
    city = str(item.get("city") or role)
    desc = str(item.get("description") or "—")
    temps = _temp_range(item)
    hint = str(item.get("hint") or "")
    line = f"{city} {desc}"
    if temps:
        line += f"，{temps}"
    if hint:
        line += f"，{hint}"
    return line


def _pick_day(raw: dict[str, Any], date: str | None) -> dict[str, Any] | None:
    days = raw.get("weather")
    if not isinstance(days, list) or not days:
        return None
    if date:
        for day in days:
            if isinstance(day, dict) and day.get("date") == date:
                return day
    first = days[0]
    return first if isinstance(first, dict) else None


def _description(raw: dict[str, Any], day: dict[str, Any] | None) -> str:
    if day:
        hourly = day.get("hourly") if isinstance(day.get("hourly"), list) else []
        preferred = {"1200", "1500", "900", "0900", "12:00"}
        for slot in hourly:
            if not isinstance(slot, dict):
                continue
            if str(slot.get("time") or "") in preferred:
                text = _desc_value(slot.get("weatherDesc"))
                if text:
                    return text
        for slot in hourly:
            if isinstance(slot, dict):
                text = _desc_value(slot.get("weatherDesc"))
                if text:
                    return text
    current = raw.get("current_condition")
    if isinstance(current, list) and current and isinstance(current[0], dict):
        return _desc_value(current[0].get("weatherDesc"))
    return ""


def _temps(raw: dict[str, Any], day: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if day:
        lo = day.get("mintempC")
        hi = day.get("maxtempC")
        if lo not in (None, "") or hi not in (None, ""):
            return (None if lo in (None, "") else str(lo), None if hi in (None, "") else str(hi))
    current = raw.get("current_condition")
    if isinstance(current, list) and current and isinstance(current[0], dict):
        temp = current[0].get("temp_C")
        if temp not in (None, ""):
            return str(temp), str(temp)
    return None, None


def _desc_value(desc: Any) -> str:
    if isinstance(desc, list) and desc and isinstance(desc[0], dict):
        return str(desc[0].get("value") or "").strip()
    return ""


def _temp_range(item: dict[str, Any]) -> str:
    lo = item.get("min_temp")
    hi = item.get("max_temp")
    if lo and hi and lo != hi:
        return f"{lo}-{hi}°C"
    if hi:
        return f"{hi}°C"
    if lo:
        return f"{lo}°C"
    return ""


def _severity(description: str) -> str:
    text = (description or "").lower()
    if any(k in text for k in SEVERE_KEYWORDS):
        return "severe"
    if any(k in text.lower() for k in WET_KEYWORDS) or any(k in description for k in WET_KEYWORDS):
        return "wet"
    return "ok"


def _city_hint(description: str) -> str:
    level = _severity(description)
    if level == "severe":
        return "注意航班延误"
    if level == "wet":
        return "建议携带雨具"
    return "适合出行"


def _trip_advice(origin_w: dict[str, Any] | None, dest_w: dict[str, Any] | None) -> str:
    parts: list[str] = []
    if origin_w:
        level = _severity(str(origin_w.get("description") or ""))
        if level == "ok":
            parts.append("出发地天气良好适合飞行")
        elif level == "wet":
            parts.append("出发地有降水，前往机场请预留时间")
        else:
            parts.append("出发地天气较差，注意航班延误")
    if dest_w:
        level = _severity(str(dest_w.get("description") or ""))
        if level == "wet":
            parts.append("目的地有降水建议携带雨具，户外活动安排在间隙")
        elif level == "severe":
            parts.append("目的地天气较差，建议减少户外安排")
        else:
            parts.append("目的地天气适宜出行")
    return "，".join(parts)
