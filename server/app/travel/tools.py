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

    flyai 往返（带 back_date）在部分日期会返回空列表，此时自动退化为单程去程，
    避免方案页空跑。
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
            if isinstance(ow.get("itemList"), list) and ow["itemList"]:
                merged = dict(ow)
                merged["roundtripFallback"] = "one_way"
                trial = str(ow.get("systemMessage") or "").strip()
                note = f"往返搜索无结果（{out.get('message') or '空'}），已改为单程去程。"
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
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


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
    return text or None


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
    price = _plain_price(
        item.get("price")
        or item.get("lowestPrice")
        or item.get("minPrice")
        or item.get("adultPrice")
        or item.get("total_price")
        or first.get("price")
        or first.get("adultPrice")
    )
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


def _fallback_plan(
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    items = _flight_items(flights_raw)[:3]
    options = []
    for idx, item in enumerate(items):
        flat = flatten_flight_item(item)
        label_bits = [p for p in (flat["flight_no"], flat["dep_time"]) if p]
        options.append(
            {
                "id": f"opt-{idx + 1}",
                "label": " ".join(label_bits) if label_bits else f"方案 {idx + 1}",
                "segments": [
                    {
                        "type": "flight",
                        "summary": segment_line(leg),
                        **{k: v for k, v in flatten_flight_item(leg).items() if v},
                    }
                    for leg in _per_journey(item)
                ],
                "total_price": flat["price"] or None,
                "notes": "基于搜索结果自动生成",
            }
        )
    total = next((o["total_price"] for o in options if o["total_price"] is not None), None)
    return {
        "options": options,
        "comparison": _comparison_from_options(options),
        "recommendation": {"option_id": options[0]["id"], "reason": "搜索结果中的首个方案"} if options else None,
        "total_price_summary": f"最低总价约 {total}" if total is not None else "暂无可比价格（搜索结果为空或失败）",
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
                    "至少 2 套方案（数据不足时合理组合）；只输出 JSON，不编造搜索结果里没有的价格。",
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
    if recommendation is None:
        recommendation = {"option_id": norm_options[0]["id"], "reason": "搜索结果中的首个方案"}
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


def _llm_flight_rows(flights_raw: dict[str, Any] | None) -> list[dict[str, str]]:
    """给规划 LLM 的扁平航班，避免把 journeys 嵌套原样塞进 prompt。"""
    rows: list[dict[str, str]] = []
    for item in _flight_items(flights_raw)[:6]:
        flat = flatten_flight_item(item)
        row = {k: v for k, v in flat.items() if v}
        row["summary"] = segment_line(item)
        rows.append(row)
    return rows


def _blank(value: Any) -> bool:
    return value in (None, "", "—", "None")


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
    payload = json.dumps(
        {
            "params": params,
            "flights": _llm_flight_rows(flights_raw),
            "hotels": hotels_raw if isinstance(hotels_raw, dict) else None,
        },
        ensure_ascii=False,
    )
    parsed = _plan_llm(payload)
    plan = _normalize_plan(parsed) if parsed else None
    if plan and _flight_items(flights_raw) and _plan_too_hollow(plan):
        plan = None
    return plan or _fallback_plan(flights_raw, hotels_raw, params)



def render_plan_html(
    plan: dict[str, Any],
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> str:
    def esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    options = [o for o in (plan.get("options") or []) if isinstance(o, dict)]
    label_by_id = {str(o.get("id") or ""): str(o.get("label") or o.get("id") or "—") for o in options}

    rows_html = ""
    for opt in options:
        segs = "；".join(
            esc(segment_line(s)) for s in (opt.get("segments") or []) if isinstance(s, dict)
        )
        rows_html += (
            f'<tr><td>{esc(opt.get("label"))}</td><td>{esc(opt.get("total_price") if opt.get("total_price") is not None else "—")}</td>'
            f'<td>{segs or "—"}</td><td>{esc(opt.get("notes") or "")}</td></tr>'
        )
    cmp_dims = [d for d in (plan.get("comparison") or []) if isinstance(d, dict)]
    if cmp_dims and (cmp_dims[0].get("rows") or []):
        col_ids = [str(r.get("option_id") or "") for r in cmp_dims[0].get("rows") or []]
    else:
        col_ids = [str(o.get("id") or "") for o in options]
    if cmp_dims and col_ids:
        head = "<tr><th>维度</th>" + "".join(
            f"<th>{esc(label_by_id.get(oid) or oid or '—')}</th>" for oid in col_ids
        ) + "</tr>"
        body = ""
        for dim in cmp_dims:
            by_id = {str(r.get("option_id") or ""): r.get("value") for r in (dim.get("rows") or []) if isinstance(r, dict)}
            cells = "".join(f"<td>{esc(by_id.get(oid, '—'))}</td>" for oid in col_ids)
            body += f"<tr><td>{esc(dim.get('dimension'))}</td>{cells}</tr>"
        cmp_html = head + body
    else:
        cmp_html = ""
    rec = plan.get("recommendation") if isinstance(plan.get("recommendation"), dict) else {}
    rec_id = str((rec or {}).get("option_id") or "")
    rec_opt = next((o for o in options if str(o.get("id") or "") == rec_id), options[0] if options else None)
    rec_label = str((rec_opt or {}).get("label") or rec_id or "—")
    rec_reason = str((rec or {}).get("reason") or "")
    rec_segs = ""
    if rec_opt:
        rec_segs = "".join(
            f"<li>{esc(segment_line(s))}</li>"
            for s in (rec_opt.get("segments") or [])
            if isinstance(s, dict)
        )
    items = _flight_items(flights_raw)
    flight_rows = "".join(f"<li>{esc(segment_line(item))}</li>" for item in items[:8])
    hotel_note = esc(
        (hotels_raw or {}).get("message") or "未搜索或未配置酒店源"
    )
    origin = str((params or {}).get("origin") or "")
    dest = str((params or {}).get("destination") or "")
    route = f"{origin} → {dest}" if origin and dest else (origin or dest or "")
    date_bits = [str(x) for x in ((params or {}).get("depart_date"), (params or {}).get("return_date")) if x]
    cabin = str((params or {}).get("cabin") or "")
    params_line = esc(" · ".join(x for x in (route, " / ".join(date_bits), cabin) if x))
    rec_list = f"<ul>{rec_segs}</ul>" if rec_segs else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>行程方案</title>
<style>
body{{font-family:"PingFang SC","Noto Sans SC",sans-serif;background:#f8fafc;color:#1e293b;margin:0;padding:24px;}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;box-shadow:0 4px 14px rgba(15,23,42,.06);padding:16px;margin-bottom:16px;}}
h1{{font-size:16px;margin:0 0 8px;}} h2{{font-size:13px;margin:0 0 8px;color:#1e293b;}}
p,td,th,li{{font-size:12.5px;}} th{{color:#64748b;font-weight:500;text-align:left;}}
table{{border-collapse:collapse;width:100%;}} td,th{{border-bottom:1px solid #e2e8f0;padding:6px 8px;vertical-align:top;}}
.rec{{background:#dbeafe;border-radius:8px;padding:8px 12px;}}
.total{{font-size:14px;font-weight:700;}}
.muted{{color:#64748b;}}
</style></head><body>
<h1>行程方案</h1><p class="muted">{params_line or "出行约束未提供"}</p>
<div class="card rec"><h2>推荐 · {esc(rec_label)}</h2><p>{esc(rec_reason)}</p>
{rec_list}
<p class="total">{esc(plan.get("total_price_summary") or "")}</p></div>
<div class="card"><h2>方案对比</h2><table>{cmp_html or '<tr><td class="muted">无对比数据</td></tr>'}</table></div>
<div class="card"><h2>可选方案</h2><table><tr><th>方案</th><th>总价</th><th>行程</th><th>备注</th></tr>{rows_html}</table></div>
<div class="card"><h2>航班搜索结果</h2><ul>{flight_rows or '<li class="muted">无机票数据</li>'}</ul></div>
<div class="card"><h2>酒店</h2><p>{hotel_note}</p></div>
</body></html>"""


def save_plan_html(
    plan: dict[str, Any],
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
    conversation_id: str | None,
) -> dict[str, Any]:
    html = render_plan_html(plan, flights_raw, hotels_raw, params)
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
