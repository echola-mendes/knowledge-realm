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
    """机票搜索：成功原样返回 flyai 响应（含 itemList）；失败返回 kind=error。"""
    try:
        return flyai.search_flights(
            origin=str(params.get("origin") or ""),
            destination=str(params.get("destination") or ""),
            dep_date=str(params.get("depart_date") or params.get("dep_date") or ""),
            back_date=params.get("return_date") or params.get("back_date") or None,
            seat_class=params.get("cabin") or params.get("seat_class") or None,
            adult_count=int(params.get("adults") or 1),
            max_price=params.get("max_price") or None,
        )
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


def _fallback_plan(
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    items = _flight_items(flights_raw)[:3]
    options = []
    for idx, item in enumerate(items):
        price = item.get("price") or item.get("minPrice") or item.get("lowestPrice")
        options.append(
            {
                "id": f"opt-{idx + 1}",
                "label": f"方案 {idx + 1}",
                "segments": [{"type": "flight", "summary": json.dumps(item, ensure_ascii=False)[:300]}],
                "total_price": price,
                "notes": "基于搜索结果自动生成",
            }
        )
    total = next((o["total_price"] for o in options if o["total_price"] is not None), None)
    return {
        "options": options,
        "comparison": [
            {
                "dimension": "总价",
                "rows": [{"option_id": o["id"], "value": o["total_price"] if o["total_price"] is not None else "—"} for o in options],
            }
        ],
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
        norm_options.append(
            {
                "id": str(opt.get("id") or f"opt-{idx + 1}"),
                "label": str(opt.get("label") or f"方案 {idx + 1}"),
                "segments": opt.get("segments") if isinstance(opt.get("segments"), list) else [],
                "total_price": opt.get("total_price"),
                "notes": str(opt.get("notes") or ""),
            }
        )
    if not norm_options:
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
    return {
        "options": norm_options,
        "comparison": comparison,
        "recommendation": recommendation,
        "total_price_summary": str(parsed.get("total_price_summary") or ""),
    }


def plan_itinerary(
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """生成可对比多套方案；LLM 失败或结构不合法时用搜索结果兜底，保证四键齐全。"""
    items = _flight_items(flights_raw)[:6]
    payload = json.dumps(
        {
            "params": params,
            "flights_itemList": items,
            "hotels": hotels_raw if isinstance(hotels_raw, dict) else None,
        },
        ensure_ascii=False,
    )
    parsed = _plan_llm(payload)
    plan = _normalize_plan(parsed) if parsed else None
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

    rows_html = ""
    for opt in plan.get("options") or []:
        segs = "；".join(
            esc(s.get("summary") or s.get("type") or "") for s in (opt.get("segments") or []) if isinstance(s, dict)
        )
        rows_html += (
            f'<tr><td>{esc(opt.get("label"))}</td><td>{esc(opt.get("total_price") if opt.get("total_price") is not None else "—")}</td>'
            f'<td>{segs or "—"}</td><td>{esc(opt.get("notes") or "")}</td></tr>'
        )
    cmp_html = ""
    for dim in plan.get("comparison") or []:
        cells = "".join(f"<th>{esc(r.get('option_id'))}</th>" for r in dim.get("rows") or [])
        vals = "".join(f"<td>{esc(r.get('value'))}</td>" for r in dim.get("rows") or [])
        cmp_html += f'<tr><th>{esc(dim.get("dimension"))}</th>{cells}</tr><tr><td></td>{vals}</tr>'
    rec = plan.get("recommendation") or {}
    items = _flight_items(flights_raw)
    flight_rows = "".join(
        f"<li><code>{esc(json.dumps(item, ensure_ascii=False))}</code></li>" for item in items[:8]
    )
    hotel_note = esc(
        (hotels_raw or {}).get("message") or "未搜索或未配置酒店源"
    )
    params_line = esc(json.dumps({k: v for k, v in (params or {}).items() if v}, ensure_ascii=False))
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>行程方案</title>
<style>
body{{font-family:"PingFang SC","Noto Sans SC",sans-serif;background:#f8fafc;color:#1e293b;margin:0;padding:24px;}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;box-shadow:0 4px 14px rgba(15,23,42,.06);padding:16px;margin-bottom:16px;}}
h1{{font-size:16px;margin:0 0 8px;}} h2{{font-size:13px;margin:0 0 8px;color:#1e293b;}}
p,td,th,li{{font-size:12.5px;}} th{{color:#64748b;font-weight:500;text-align:left;}}
table{{border-collapse:collapse;width:100%;}} td,th{{border-bottom:1px solid #e2e8f0;padding:6px 8px;vertical-align:top;}}
.rec{{background:#dbeafe;border-radius:8px;padding:8px 12px;}}
.total{{font-size:14px;font-weight:700;}} code{{font-family:ui-monospace,monospace;font-size:11px;word-break:break-all;}}
.muted{{color:#64748b;}}
</style></head><body>
<h1>行程方案</h1><p class="muted">约束：{params_line}</p>
<div class="card rec"><h2>推荐</h2><p>{esc(rec.get("option_id") or "—")}：{esc(rec.get("reason") or "")}</p>
<p class="total">{esc(plan.get("total_price_summary") or "")}</p></div>
<div class="card"><h2>方案对比</h2><table>{cmp_html or '<tr><td class="muted">无对比数据</td></tr>'}</table></div>
<div class="card"><h2>可选方案</h2><table><tr><th>方案</th><th>总价</th><th>行程</th><th>备注</th></tr>{rows_html}</table></div>
<div class="card"><h2>航班搜索结果（flyai itemList）</h2><ul>{flight_rows or '<li class="muted">无机票数据</li>'}</ul></div>
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
