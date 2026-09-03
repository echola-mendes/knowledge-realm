"""TRAVEL-PLAN-1 差旅工具：机票/酒店搜索、方案生成、方案页上传。

契约要点（PRD-P4 §4 / architecture.md §5）：
- 机票：flyai 响应 **原样透传**，前端卡片绑 `itemList`；
- 酒店：`HOTEL_SOURCE` 未配置时返回 `{kind:"placeholder"}`，禁止伪造房型；
- `plan_itinerary` 输出 `{options, comparison, recommendation, total_price_summary}`，不绑 flyai 字段；
- `save_plan_html` 渲染 HTML → MinIO `plans/{conversation_id}/...`（软依赖，失败仅提示）。
"""
from __future__ import annotations

import json
from typing import Any

from app.travel import flyai, minio_store

HOTEL_PLACEHOLDER = {
    "kind": "placeholder",
    "message": "酒店供应商未配置，暂不支持酒店搜索与房型报价（配置 HOTEL_SOURCE 后可用）。",
}


def search_flights_tool(params: dict[str, Any]) -> dict[str, Any]:
    """机票搜索：成功原样返回 flyai 响应（含 itemList）；失败返回 kind=error。

    flyai 往返（带 back_date）在部分日期会返回空列表，此时退化为两次单程
    （去程 + 返程各搜一次），避免方案页空跑或 LLM 编造返程。
    """
    origin = str(params.get("origin") or "")
    destination = str(params.get("destination") or "")
    dep_date = str(params.get("depart_date") or params.get("dep_date") or "")
    back_date = params.get("return_date") or params.get("back_date") or None
    seat_class = params.get("cabin") or params.get("seat_class") or None
    adult_count = int(params.get("adults") or 1)
    max_price = params.get("max_price") or None
    try:
        out = flyai.search_flights(
            origin=origin,
            destination=destination,
            dep_date=dep_date,
            back_date=back_date,
            seat_class=seat_class,
            adult_count=adult_count,
            max_price=max_price,
        )
        items = out.get("itemList") if isinstance(out.get("itemList"), list) else []
        if back_date and not items:
            ow = flyai.search_flights(
                origin=origin,
                destination=destination,
                dep_date=dep_date,
                back_date=None,
                seat_class=seat_class,
                adult_count=adult_count,
                max_price=max_price,
            )
            out_items = ow.get("itemList") if isinstance(ow.get("itemList"), list) else []
            ret_items: list[dict[str, Any]] = []
            ret = flyai.search_flights(
                origin=destination,
                destination=origin,
                dep_date=str(back_date),
                back_date=None,
                seat_class=seat_class,
                adult_count=adult_count,
                max_price=max_price,
            )
            ret_items = ret.get("itemList") if isinstance(ret.get("itemList"), list) else []
            if out_items:
                merged = dict(ow)
                merged["itemList"] = out_items
                merged["returnItemList"] = ret_items
                merged["roundtripFallback"] = "split_one_way"
                trial = str(ow.get("systemMessage") or "").strip()
                note = f"往返联程无结果（{out.get('message') or '空'}），已改为去程+返程分别搜索。"
                if not ret_items:
                    note += " 返程未搜到航班，方案仅含去程。"
                merged["systemMessage"] = f"{note} {trial}".strip() if trial else note
                return merged
        return out
    except flyai.FlyaiError as exc:
        return {"kind": "error", "message": str(exc)}


def hotel_source_enabled() -> bool:
    from app.config import get_settings

    return get_settings().hotel_source == "flyai"


def search_hotels_tool(params: dict[str, Any]) -> dict[str, Any]:
    """酒店搜索：未配置供应商时占位提示，不伪造房型。"""
    if not hotel_source_enabled():
        return dict(HOTEL_PLACEHOLDER)
    try:
        return flyai.search_hotels(
            dest_name=str(params.get("destination") or params.get("dest_name") or ""),
            check_in_date=str(params.get("check_in_date") or params.get("depart_date") or ""),
            check_out_date=str(params.get("check_out_date") or params.get("return_date") or ""),
            poi_name=params.get("poi_name") or None,
            hotel_stars=params.get("hotel_stars") or None,
            max_price=params.get("max_price") or None,
        )
    except flyai.FlyaiError as exc:
        return {"kind": "error", "message": str(exc)}


def _flight_items(flights_raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = (flights_raw or {}).get("itemList")
    return _dedupe_flight_items(
        [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    )


def _return_flight_items(flights_raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = (flights_raw or {}).get("returnItemList")
    return _dedupe_flight_items(
        [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    )


def _flight_signature(item: dict[str, Any]) -> tuple[str, str, str, str]:
    flat = flatten_flight_item(item)
    return (flat["flight_no"], flat["dep_time"], flat["dep_place"], flat["arr_place"])


def _dedupe_flight_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        sig = _flight_signature(item)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)
    return out


def _pick(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = obj.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _time_short(value: str) -> str:
    text = value.strip()
    if " " in text:
        return text.split()[-1][:5]
    if ":" in text:
        return text[:5]
    return text


def _station(obj: dict[str, Any], prefix: str) -> str:
    name = _pick(
        obj,
        f"{prefix}StationShortName",
        f"{prefix}Airport",
        f"{prefix}AirportName",
        f"{prefix}City",
        f"{prefix}CityName",
        f"{prefix}StationName",
        f"{prefix}Place",
    )
    term = _pick(obj, f"{prefix}Term")
    if name and term:
        return f"{name}{term}"
    return name


def _plain_price(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).replace("¥", "").replace(",", "").strip()
    if not text or text in ("—", "-", "null", "None"):
        return None
    try:
        if float(text) <= 0:
            return None
    except ValueError:
        pass
    return text


_PRICE_KEYS = (
    "adultPrice",
    "adultTaxPrice",
    "price",
    "lowestPrice",
    "minPrice",
    "lowestAdultPrice",
    "ticketPrice",
    "totalPrice",
    "showPrice",
    "salePrice",
    "childPrice",
)


def _extract_price(obj: dict[str, Any]) -> str | None:
    """从 flyai item / journey / segment 抽取票价（兼容多种字段名与嵌套）。"""
    for key in _PRICE_KEYS:
        raw = obj.get(key)
        if isinstance(raw, dict):
            continue
        val = _plain_price(raw)
        if val:
            return val
    nested = obj.get("price")
    if isinstance(nested, dict):
        for key in _PRICE_KEYS:
            val = _plain_price(nested.get(key))
            if val:
                return val
    elif nested is not None:
        val = _plain_price(nested)
        if val:
            return val
    journeys = obj.get("journeys")
    if isinstance(journeys, list):
        parts: list[float] = []
        for journey in journeys:
            if not isinstance(journey, dict):
                continue
            seg_price = _extract_price(journey)
            if seg_price:
                try:
                    parts.append(float(seg_price))
                except ValueError:
                    pass
        if len(parts) == 1:
            return _plain_price(parts[0])
        if len(parts) > 1:
            total = sum(parts)
            return _plain_price(total) if total > 0 else None
    return None


def _sum_prices(*values: str | None) -> str | None:
    nums: list[float] = []
    for value in values:
        if not value:
            continue
        try:
            nums.append(float(value))
        except ValueError:
            return None
    if not nums:
        return None
    return _plain_price(sum(nums))


def _legs(item: dict[str, Any]) -> list[dict[str, Any]]:
    """单程航段：取 journeys[0].segments（中转拼第一程）；无 journeys 则 item 自身。"""
    journeys = item.get("journeys")
    if isinstance(journeys, list) and journeys:
        first = journeys[0] if isinstance(journeys[0], dict) else None
        segs = first.get("segments") if first else None
        if isinstance(segs, list):
            legs = [seg for seg in segs if isinstance(seg, dict)]
            if legs:
                return legs
    return [item]


def _per_journey(item: dict[str, Any]) -> list[dict[str, Any]]:
    """往返拆成多段，便于方案里同时写出程/返程。"""
    journeys = item.get("journeys")
    if isinstance(journeys, list) and len(journeys) > 1:
        rows: list[dict[str, Any]] = []
        for journey in journeys:
            if isinstance(journey, dict):
                row = {k: v for k, v in item.items() if k != "journeys"}
                row["journeys"] = [journey]
                rows.append(row)
        if rows:
            return rows
    return [item]


def flatten_flight_item(item: dict[str, Any]) -> dict[str, str]:
    """从 flyai item 或方案 segment 抽出可读航班字段（不改原 item）。"""
    legs = _legs(item)
    first, last = legs[0], legs[-1]
    price = _extract_price(item) or _extract_price(first) or _plain_price(item.get("total_price"))
    return {
        "airline": _pick(first, "marketingTransportName", "airlineName", "airline")
        or _pick(item, "airlineName", "airline", "airline"),
        "flight_no": _pick(first, "marketingTransportNo", "flightNo", "flightNoCn", "trainNo", "flight_no")
        or _pick(item, "flightNo", "flightNoCn", "trainNo", "flight_no"),
        "dep_time": _time_short(_pick(first, "depDateTime", "depTime", "dep_time")),
        "arr_time": _time_short(_pick(last, "arrDateTime", "arrTime", "arr_time")),
        "dep_place": _station(first, "dep") or _pick(first, "dep_place") or _pick(item, "dep_place"),
        "arr_place": _station(last, "arr") or _pick(last, "arr_place") or _pick(item, "arr_place"),
        "price": price or "",
        "cabin": _pick(first, "seatClassName", "cabin") or _pick(item, "cabin"),
    }


def segment_line(seg: dict[str, Any] | str) -> str:
    """方案环节 / 机票条目的一行可读摘要。"""
    if isinstance(seg, str):
        return seg.strip()
    summary = seg.get("summary") or seg.get("detail") or seg.get("description")
    if isinstance(summary, str) and summary.strip():
        raw = summary.strip()
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return segment_line(parsed)
            except json.JSONDecodeError:
                pass
            return raw[:120]
        return raw
    flat = flatten_flight_item(seg)
    bits = [
        p
        for p in (
            flat["flight_no"],
            f"{flat['dep_place']}→{flat['arr_place']}" if flat["dep_place"] or flat["arr_place"] else "",
            f"{flat['dep_time']}–{flat['arr_time']}" if flat["dep_time"] or flat["arr_time"] else "",
            f"¥{flat['price']}" if flat["price"] else "",
        )
        if p
    ]
    if bits:
        return " ".join(bits)
    return str(seg.get("type") or "行程")


def _normalize_segment(seg: Any) -> dict[str, Any] | None:
    if isinstance(seg, str) and seg.strip():
        return {"type": "flight", "summary": seg.strip()}
    if not isinstance(seg, dict):
        return None
    line = segment_line(seg)
    out: dict[str, Any] = {"type": str(seg.get("type") or "flight"), "summary": line}
    price = _plain_price(seg.get("price") or seg.get("adultPrice") or seg.get("total_price") or flatten_flight_item(seg)["price"])
    if price:
        out["price"] = price
    if seg.get("leg"):
        out["leg"] = str(seg.get("leg"))
    return out


def _comparison_from_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从方案 segments / 总价拼可读对比表（航班、时刻、行程、总价）。"""
    if not options:
        return []

    def _bits(opt: dict[str, Any]) -> dict[str, str]:
        flights: list[str] = []
        times: list[str] = []
        routes: list[str] = []
        lines: list[str] = []
        for seg in opt.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            line = segment_line(seg)
            if line:
                lines.append(line)
            flat = flatten_flight_item(seg)
            if flat["flight_no"]:
                flights.append(flat["flight_no"])
            elif line:
                token = line.split()[0]
                if token and token not in ("行程", "flight"):
                    flights.append(token)
            if flat["dep_time"] or flat["arr_time"]:
                times.append(f"{flat['dep_time']}–{flat['arr_time']}".strip("–"))
            if flat["dep_place"] or flat["arr_place"]:
                routes.append(f"{flat['dep_place']}→{flat['arr_place']}")
        return {
            "flight": " / ".join(flights) or "—",
            "time": " / ".join(times) or "—",
            "route": " / ".join(routes) or "—",
            "trip": "；".join(lines) or "—",
            "price": str(opt["total_price"]) if opt.get("total_price") not in (None, "") else "—",
        }

    bits = [_bits(o) for o in options]
    dims: list[tuple[str, str]] = [("航班", "flight"), ("时刻", "time"), ("航线", "route"), ("行程", "trip"), ("总价", "price")]
    out: list[dict[str, Any]] = []
    for label, key in dims:
        rows = [{"option_id": o["id"], "value": bits[i][key]} for i, o in enumerate(options)]
        if all(r["value"] in ("—", "", None) for r in rows):
            continue
        # 行程与航班/时刻重复时，有航班或时刻就跳过整行行程
        if key == "trip" and any(bits[i]["flight"] != "—" or bits[i]["time"] != "—" for i in range(len(options))):
            continue
        out.append({"dimension": label, "rows": rows})
    return out


def _option_from_items(
    idx: int,
    outbound: dict[str, Any],
    inbound: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_flat = flatten_flight_item(outbound)
    label_bits = [p for p in (out_flat["flight_no"], out_flat["dep_time"]) if p]
    segments: list[dict[str, Any]] = [
        {
            "type": "flight",
            "leg": "outbound",
            "summary": segment_line(outbound),
            **{k: v for k, v in out_flat.items() if v},
        }
    ]
    total = out_flat["price"] or None
    if inbound:
        in_flat = flatten_flight_item(inbound)
        segments.append(
            {
                "type": "flight",
                "leg": "return",
                "summary": segment_line(inbound),
                **{k: v for k, v in in_flat.items() if v},
            }
        )
        total = _sum_prices(out_flat["price"], in_flat["price"])
    return {
        "id": f"opt-{idx + 1}",
        "label": " ".join(label_bits) if label_bits else f"方案 {idx + 1}",
        "segments": segments,
        "total_price": total,
        "notes": "基于搜索结果自动生成",
    }



def _price_number(value: Any) -> float | None:
    if value in (None, "", "—"):
        return None
    raw = str(value).replace("¥", "").replace(",", "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


_WEAK_RECOMMEND_REASONS = (
    "搜索结果中的首个方案",
    "搜索结果的第一套方案",
    "首个方案",
    "第一套方案",
    "第一个方案",
)


def _recommend_reason_from_options(
    options: list[dict[str, Any]],
    preferred_id: str | None = None,
) -> str:
    """兜底推荐理由：用总价/标签说明，禁止「第一套」这类空话。"""
    if not options:
        return "暂无可用方案"
    rec = next((o for o in options if str(o.get("id") or "") == str(preferred_id or "")), options[0])
    label = str(rec.get("label") or "").strip()
    rec_price = _price_number(rec.get("total_price"))
    priced = [(o, _price_number(o.get("total_price"))) for o in options]
    priced_ok = [(o, p) for o, p in priced if p is not None]
    if rec_price is not None and priced_ok:
        min_price = min(p for _, p in priced_ok)
        if rec_price <= min_price + 1e-6:
            return f"当前可比方案中总价最低（¥{rec_price:g}）"
    if label:
        return f"综合搜索结果优先推荐「{label}」"
    return "按当前搜索排序靠前的可比方案"


def _coerce_recommendation(
    options: list[dict[str, Any]],
    recommendation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not options:
        return None
    rec = dict(recommendation) if isinstance(recommendation, dict) else {}
    oid = str(rec.get("option_id") or "")
    if not oid or oid not in {str(o.get("id") or "") for o in options}:
        oid = str(options[0].get("id") or "")
    reason = str(rec.get("reason") or "").strip()
    if (not reason) or reason in _WEAK_RECOMMEND_REASONS or any(w in reason for w in ("第一套", "首个方案", "第一个方案")):
        reason = _recommend_reason_from_options(options, oid)
    return {"option_id": oid, "reason": reason}

def _fallback_plan(
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    outbound = _flight_items(flights_raw)[:3]
    inbound = _return_flight_items(flights_raw)
    options: list[dict[str, Any]] = []
    if inbound:
        for idx, (out_item, in_item) in enumerate(zip(outbound, inbound)):
            options.append(_option_from_items(idx, out_item, in_item))
    else:
        for idx, item in enumerate(outbound):
            legs = _per_journey(item)
            if len(legs) >= 2:
                options.append(_option_from_items(idx, legs[0], legs[1]))
            else:
                options.append(_option_from_items(idx, legs[0]))
    total = next((o["total_price"] for o in options if o["total_price"] is not None), None)
    return {
        "options": options,
        "comparison": _comparison_from_options(options),
        "recommendation": _coerce_recommendation(options, None),
        "total_price_summary": f"最低总价约 ¥{total}" if total is not None else "暂无可比价格（搜索结果为空或失败）",
    }


def _plan_llm(payload: str) -> dict[str, Any] | None:
    """一次 LLM 结构化生成方案；失败返回 None 走兜底。可被测试替换。"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
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
                    "你是行程规划师。根据搜索结果与用户约束输出**可对比多套方案**的 JSON，"
                    '格式：{"options":[{"id","label","segments","total_price","notes"}],'
                    '"comparison":[{"dimension","rows":[{"option_id","value"}]}],'
                    '"recommendation":{"option_id","reason"},"total_price_summary":"..."}。'
                    "segments 每项必须有可读 summary（航班号、机场、时刻、票价），不得只给内部字段。"
                    "return_flights 为空时禁止编造返程；有 return_flights 时去程+返程各取一条组成方案。"
                    "comparison.rows[].option_id 必须与 options[].id 一致（如 opt-1）。"
                    "至少 2 套方案（数据不足时合理组合）；只输出 JSON，不编造搜索结果里没有的价格。"
                ),
                ("human", "{payload}"),
            ]
        )
        resp = (prompt | model).invoke({"payload": payload})
        raw = str(resp.content)
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if 0 <= start <= end else raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None



def _remap_comparison(
    comparison: list[dict[str, Any]],
    options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将 LLM 错写的 option_id 映射回 options[].id（按 id/label/行序兜底）。"""
    by_id = {str(o.get("id") or ""): str(o.get("id") or "") for o in options}
    by_label = {str(o.get("label") or ""): str(o.get("id") or "") for o in options}
    valid = set(by_id)
    out: list[dict[str, Any]] = []
    for dim in comparison:
        if not isinstance(dim, dict):
            continue
        rows: list[dict[str, Any]] = []
        for idx, row in enumerate(dim.get("rows") or []):
            if not isinstance(row, dict):
                continue
            oid = str(row.get("option_id") or "")
            if oid in valid:
                mapped = oid
            elif oid in by_label:
                mapped = by_label[oid]
            elif idx < len(options):
                mapped = str(options[idx].get("id") or "")
            else:
                mapped = oid
            rows.append({"option_id": mapped, "value": row.get("value")})
        out.append({"dimension": str(dim.get("dimension") or ""), "rows": rows})
    return out


def _normalize_plan(parsed: dict[str, Any]) -> dict[str, Any] | None:
    options = parsed.get("options")
    if not isinstance(options, list) or not options:
        return None
    norm_options = []
    for idx, opt in enumerate(options):
        if not isinstance(opt, dict):
            continue
        segs = [_normalize_segment(s) for s in (opt.get("segments") or [])]
        segs = [s for s in segs if s]
        norm_options.append(
            {
                "id": str(opt.get("id") or f"opt-{idx + 1}"),
                "label": str(opt.get("label") or f"方案 {idx + 1}"),
                "segments": segs,
                "total_price": _plain_price(opt.get("total_price")) or opt.get("total_price"),
                "notes": str(opt.get("notes") or ""),
            }
        )
    if not norm_options:
        return None
    if not any(o["segments"] for o in norm_options):
        return None
    comparison = [
        {
            "dimension": str(c.get("dimension") or ""),
            "rows": [
                {"option_id": str(r.get("option_id") or ""), "value": r.get("value")}
                for r in (c.get("rows") or [])
                if isinstance(r, dict)
            ],
        }
        for c in (parsed.get("comparison") or [])
        if isinstance(c, dict)
    ]
    rec = parsed.get("recommendation")
    recommendation = (
        {"option_id": str(rec.get("option_id") or ""), "reason": str(rec.get("reason") or "")}
        if isinstance(rec, dict)
        else None
    )
    if not comparison:
        comparison = _comparison_from_options(norm_options)
    else:
        comparison = _remap_comparison(comparison, norm_options)
    recommendation = _coerce_recommendation(norm_options, recommendation)
    summary = str(parsed.get("total_price_summary") or "")
    if not summary:
        priced = [o["total_price"] for o in norm_options if o.get("total_price") not in (None, "")]
        summary = f"最低总价约 {priced[0]}" if priced else ""
    return {
        "options": norm_options,
        "comparison": comparison,
        "recommendation": recommendation,
        "total_price_summary": summary,
    }


def _llm_flight_rows(
    flights_raw: dict[str, Any] | None, *, leg: str = "outbound"
) -> list[dict[str, str]]:
    """给规划 LLM 的扁平航班，避免把 journeys 嵌套原样塞进 prompt。"""
    items = _return_flight_items(flights_raw) if leg == "return" else _flight_items(flights_raw)
    rows: list[dict[str, str]] = []
    for item in items[:6]:
        flat = flatten_flight_item(item)
        row = {k: v for k, v in flat.items() if v}
        row["summary"] = segment_line(item)
        row["leg"] = leg
        rows.append(row)
    return rows


def _blank(value: Any) -> bool:
    return value in (None, "", "—", "None")




def _flight_segments(segments: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if str(seg.get("type") or "flight").lower() == "hotel":
            continue
        out.append(seg)
    return out


def _return_source_items(flights_raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = _return_flight_items(flights_raw)
    if items:
        return items
    pooled: list[dict[str, Any]] = []
    for item in _flight_items(flights_raw):
        legs = _per_journey(item)
        if len(legs) >= 2:
            pooled.append(legs[1])
    return pooled


def _ensure_roundtrip_segments(
    plan: dict[str, Any],
    flights_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """往返行程：补全缺失的返程 segment（LLM 常只写去程）。"""
    if not str(params.get("return_date") or "").strip():
        return plan
    return_items = _return_source_items(flights_raw)
    if not return_items:
        return plan
    options = [o for o in (plan.get("options") or []) if isinstance(o, dict)]
    if not options:
        return plan
    changed = False
    for idx, opt in enumerate(options):
        segs = [dict(s) for s in (opt.get("segments") or []) if isinstance(s, dict)]
        if len(_flight_segments(segs)) >= 2:
            continue
        ret_item = return_items[min(idx, len(return_items) - 1)]
        in_flat = flatten_flight_item(ret_item)
        ret_seg = _normalize_segment(
            {
                "type": "flight",
                "leg": "return",
                "summary": segment_line(ret_item),
                **{k: v for k, v in in_flat.items() if v},
            }
        )
        if not ret_seg:
            continue
        new_segs: list[dict[str, Any]] = []
        for seg in segs:
            seg_copy = dict(seg)
            if str(seg_copy.get("type") or "flight").lower() != "hotel" and seg_copy.get("leg") != "return":
                seg_copy.setdefault("leg", "outbound")
            new_segs.append(seg_copy)
        if len(_flight_segments(new_segs)) < 2:
            new_segs.append(ret_seg)
        opt["segments"] = new_segs
        flights = _flight_segments(new_segs)
        out_price = None
        if flights:
            out_price = _plain_price(flights[0].get("price") or flatten_flight_item(flights[0]).get("price"))
        in_price = in_flat.get("price") or None
        total = _sum_prices(out_price, in_price)
        if total:
            opt["total_price"] = total
        changed = True
    if changed:
        plan["options"] = options
        plan["comparison"] = _comparison_from_options(options)
    return plan

def _plan_too_hollow(plan: dict[str, Any]) -> bool:
    """LLM 方案缺价格/对比时视为空，改走搜索结果兜底。"""
    options = plan.get("options") or []
    if not options or not any(o.get("segments") for o in options):
        return True
    if not any(not _blank(o.get("total_price")) for o in options):
        return True
    rows = [r for dim in (plan.get("comparison") or []) for r in (dim.get("rows") or [])]
    if not rows or all(_blank(r.get("value")) for r in rows):
        return True
    return False


def plan_itinerary(
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """生成可对比多套方案；LLM 失败、结构不合法或空方案时用搜索结果兜底。"""
    return_flights = _return_flight_items(flights_raw)
    payload = json.dumps(
        {
            "params": params,
            "outbound_flights": _llm_flight_rows(flights_raw, leg="outbound"),
            "return_flights": _llm_flight_rows(flights_raw, leg="return") if return_flights else [],
            "roundtrip_fallback": (flights_raw or {}).get("roundtripFallback"),
            "hotels": hotels_raw if isinstance(hotels_raw, dict) else None,
        },
        ensure_ascii=False,
    )
    parsed = _plan_llm(payload)
    plan = _normalize_plan(parsed) if parsed else None
    if plan and _flight_items(flights_raw) and _plan_too_hollow(plan):
        plan = None
    plan = plan or _fallback_plan(flights_raw, hotels_raw, params)
    return _ensure_roundtrip_segments(plan, flights_raw, params)



def render_plan_html(
    plan: dict[str, Any],
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
    weather: dict[str, Any] | None = None,
) -> str:
    from app.travel.plan_page_html import render_plan_html as _render

    return _render(plan, flights_raw, hotels_raw, params, weather=weather)

def save_plan_html(
    plan: dict[str, Any],
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
    conversation_id: str | None,
) -> dict[str, Any]:
    from app.travel import weather as weather_mod

    params = params or {}
    trip_weather = weather_mod.fetch_trip_weather(
        params.get("origin"),
        params.get("destination"),
        params.get("depart_date") or params.get("dep_date"),
        params.get("return_date"),
    )
    html = render_plan_html(plan, flights_raw, hotels_raw, params, weather=trip_weather)
    upload = minio_store.put_plan_html(conversation_id, html) if minio_store.minio_ready() else None
    if upload:
        note = "方案页已存 MinIO，可回看（链接 7 天有效）。"
    elif not minio_store.minio_ready():
        note = "MinIO 未配置：方案页仅本次会话实时展示，历史回看不可用。"
    else:
        note = "MinIO 上传失败：方案页仅本次会话实时展示。"
    return {
        "html": html,
        "url": (upload or {}).get("url"),
        "key": (upload or {}).get("key"),
        "note": note,
    }
