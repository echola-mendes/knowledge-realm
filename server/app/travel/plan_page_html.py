"""行程方案页 HTML 渲染（对齐 gogo-agent html-plan skill 结构与样式）。"""
from __future__ import annotations

from typing import Any


def _esc(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _price_cell(value: Any) -> str:
    if value in (None, "", "—"):
        return "—"
    text = str(value).strip()
    if text.startswith("¥"):
        return f'<span class="price">{_esc(text)}</span>'
    return f'<span class="price">¥{_esc(text)}</span>'


def _travel_tools():
    from app.travel import tools as travel_tools

    return travel_tools


def _split_segments(segments: list[Any]) -> tuple[str, str, str]:
    segment_line = _travel_tools().segment_line
    outbound = ""
    inbound = ""
    hotel = ""
    flights: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        line = segment_line(seg)
        leg = str(seg.get("leg") or "").lower()
        seg_type = str(seg.get("type") or "flight").lower()
        if seg_type == "hotel":
            hotel = line
            continue
        if leg == "return":
            inbound = line
            continue
        if leg == "outbound":
            outbound = line
            continue
        if seg_type == "flight" or seg.get("flight_no") or seg.get("summary"):
            flights.append(line)
        elif line:
            flights.append(line)
    for line in flights:
        if not outbound:
            outbound = line
        elif not inbound:
            inbound = line
    return outbound, inbound, hotel


def _segment_price(seg: dict[str, Any]) -> str | None:
    for key in ("price", "adultPrice", "total_price"):
        val = seg.get(key)
        if val not in (None, ""):
            return str(val).replace("¥", "").strip()
    flat = _travel_tools().flatten_flight_item(seg)
    return flat["price"] or None


def _candidate_stats(
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
) -> dict[str, int | str]:
    tt = _travel_tools()
    outbound = len(tt._flight_items(flights_raw))
    inbound = len(tt._return_flight_items(flights_raw))
    hotels = 0
    hotel_note = ""
    if isinstance(hotels_raw, dict):
        if hotels_raw.get("kind") == "placeholder":
            hotel_note = "未配置"
        elif hotels_raw.get("kind") == "error":
            hotel_note = "搜索失败"
        else:
            items = hotels_raw.get("itemList") or hotels_raw.get("hotels") or []
            if isinstance(items, list):
                hotels = len(items)
    return {
        "outbound": outbound,
        "inbound": inbound,
        "hotels": hotels,
        "hotel_note": hotel_note,
    }




_VENDOR_NOISE = ("体验模式", "flyai.open", "API Key", "开放平台", "申请完整", "api key")


def _vendor_ops_note(message: str | None) -> str:
    """供应商 systemMessage 只保留业务提示，去掉体验模式/开放平台营销。"""
    text = str(message or "").strip()
    if not text:
        return ""
    kept: list[str] = []
    for chunk in text.replace("。", "。\n").split("\n"):
        piece = chunk.strip()
        if not piece:
            continue
        low = piece.lower()
        if any(marker.lower() in low for marker in _VENDOR_NOISE):
            continue
        kept.append(piece)
    return "".join(kept).strip()


def _weather_item_html(role: str, item: dict[str, Any]) -> tuple[str, str]:
    from app.travel.weather import format_weather_item

    city = str(item.get("city") or role)
    line = format_weather_item(item, role)
    rest = line[len(city):].lstrip(" ，") if line.startswith(city) else line
    html = (
        f'<div class="weather-item">🌤️ <strong>{_esc(role)} · {_esc(city)}</strong>'
        f"{' ' + _esc(rest) if rest else ''}</div>"
    )
    return html, line


def _weather_block(weather: dict[str, Any] | None) -> tuple[str, str]:
    """推荐方案下的出发地/目的地天气卡片；无数据则空。"""
    if not isinstance(weather, dict):
        return "", ""
    origin = weather.get("origin") if isinstance(weather.get("origin"), dict) else None
    dest = weather.get("destination") if isinstance(weather.get("destination"), dict) else None
    if origin and dest and origin.get("city") == dest.get("city"):
        dest = dest if origin is not dest else None
        if dest and origin.get("description") == dest.get("description"):
            dest = None
    items: list[str] = []
    summary_bits: list[str] = []
    if origin:
        html, line = _weather_item_html("出发地", origin)
        items.append(html)
        summary_bits.append(line)
    if dest:
        html, line = _weather_item_html("目的地", dest)
        items.append(html)
        summary_bits.append(line)
    if not items:
        return "", ""
    advice = str(weather.get("advice") or "").strip()
    advice_html = (
        f'<div class="recommend-reason"><strong>🌤️ 天气提醒</strong>：{_esc(advice)}</div>'
        if advice
        else ""
    )
    return f'<div class="weather-box">{"".join(items)}</div>{advice_html}', " / ".join(summary_bits)


def render_plan_html(
    plan: dict[str, Any],
    flights_raw: dict[str, Any] | None,
    hotels_raw: dict[str, Any] | None,
    params: dict[str, Any],
    weather: dict[str, Any] | None = None,
) -> str:
    options = [o for o in (plan.get("options") or []) if isinstance(o, dict)]
    rec = plan.get("recommendation") if isinstance(plan.get("recommendation"), dict) else {}
    rec_id = str((rec or {}).get("option_id") or "")
    rec_opt = next((o for o in options if str(o.get("id") or "") == rec_id), options[0] if options else None)

    origin = str((params or {}).get("origin") or "")
    dest = str((params or {}).get("destination") or "")
    route = f"{origin} → {dest}" if origin and dest else (origin or dest or "行程")
    depart = str((params or {}).get("depart_date") or "")
    ret = str((params or {}).get("return_date") or "")
    cabin = str((params or {}).get("cabin") or "")
    date_line = " / ".join(x for x in (f"{depart} 去" if depart else "", f"{ret} 返" if ret else "") if x)
    meta_bits = [x for x in (route, date_line, cabin) if x]

    rec_label = str((rec_opt or {}).get("label") or rec_id or "—")
    rec_reason = str((rec or {}).get("reason") or "")
    weather_html, weather_summary = _weather_block(weather)

    cost_rows = ""
    if rec_opt:
        segs = [s for s in (rec_opt.get("segments") or []) if isinstance(s, dict)]
        out_line, in_line, hotel_line = _split_segments(segs)
        out_price = _segment_price(segs[0]) if segs else None
        in_price = _segment_price(segs[1]) if len(segs) > 1 else None
        if out_line:
            cost_rows += (
                f"<tr><td>🛫 去程</td><td>{_esc(out_line)}</td>"
                f"<td>{_price_cell(out_price) if out_price else '—'}</td></tr>"
            )
        if in_line:
            cost_rows += (
                f"<tr><td>🛬 返程</td><td>{_esc(in_line)}</td>"
                f"<td>{_price_cell(in_price) if in_price else '—'}</td></tr>"
            )
        if hotel_line:
            cost_rows += f"<tr><td>🏨 酒店</td><td>{_esc(hotel_line)}</td><td>—</td></tr>"
        total = rec_opt.get("total_price")
        total_detail = _esc(plan.get("total_price_summary") or "")
        cost_rows += (
            f'<tr class="total-row"><td><strong>合计</strong></td>'
            f"<td>{total_detail or '—'}</td>"
            f"<td>{_price_cell(total)}</td></tr>"
        )

    cmp_rows = ""
    for idx, opt in enumerate(options):
        oid = str(opt.get("id") or f"opt-{idx + 1}")
        is_rec = oid == rec_id or (not rec_id and idx == 0)
        out_line, in_line, hotel_line = _split_segments(
            [s for s in (opt.get("segments") or []) if isinstance(s, dict)]
        )
        name = f"方案{idx + 1}" + (" ✅推荐" if is_rec else "")
        audit = "✅ 可参考" if is_rec else "—"
        cmp_rows += (
            f"<tr{' class=\"recommended\"' if is_rec else ''}>"
            f"<td>{_esc(name)}</td>"
            f"<td>{_esc(opt.get('label') or '—')}</td>"
            f"<td>{_esc(out_line or '—')}</td>"
            f"<td>{_esc(in_line or '—')}</td>"
            f"<td>{_esc(hotel_line or '—')}</td>"
            f"<td>—</td>"
            f"<td>{_price_cell(opt.get('total_price'))}</td>"
            f"<td>—</td>"
            f"<td>{audit}</td>"
            f"</tr>"
        )

    detail_blocks = ""
    for idx, opt in enumerate(options):
        oid = str(opt.get("id") or f"opt-{idx + 1}")
        is_rec = oid == rec_id or (not rec_id and idx == 0)
        status_cls = "recommended" if is_rec else ""
        badge = '<span class="badge badge-success">✅ 推荐</span>' if is_rec else ""
        out_line, in_line, hotel_line = _split_segments(
            [s for s in (opt.get("segments") or []) if isinstance(s, dict)]
        )
        lines: list[str] = []
        if out_line:
            lines.append(f"<li>去程：{_esc(out_line)}</li>")
        if in_line:
            lines.append(f"<li>返程：{_esc(in_line)}</li>")
        if hotel_line:
            lines.append(f"<li>酒店：{_esc(hotel_line)}</li>")
        notes = str(opt.get("notes") or "").strip()
        note_html = f'<p class="plan-note success">{_esc(notes)}</p>' if notes else ""
        detail_blocks += (
            f'<div class="plan-item {status_cls}">'
            f'<h3>方案{idx + 1} · {_esc(opt.get("label") or oid)} {badge}</h3>'
            f"<ul>{''.join(lines) or '<li class=\"muted\">—</li>'}</ul>"
            f"<p>总价：{_price_cell(opt.get('total_price'))}</p>"
            f"{note_html}"
            f"</div>"
        )

    stats = _candidate_stats(flights_raw, hotels_raw)
    hotel_stat = (
        str(stats["hotel_note"])
        if stats["hotel_note"]
        else (f"{stats['hotels']} 条" if stats["hotels"] else "未搜索")
    )
    agent_items: list[str] = []
    if weather_summary:
        agent_items.append(f"环境感知：查询了出发地与目的地天气（{weather_summary}）")
    agent_items += [
        f"候选检索：去程 {stats['outbound']} 条"
        + (f"、返程 {stats['inbound']} 条" if stats["inbound"] else "")
        + f"、酒店 {hotel_stat}",
        f"方案组合：共 {len(options)} 套可比方案",
    ]
    if rec_reason:
        agent_items.append(f"推荐依据：{rec_reason}")
    ops_note = _vendor_ops_note((flights_raw or {}).get("systemMessage") if isinstance(flights_raw, dict) else None)
    if ops_note:
        agent_items.append(f"检索说明：{ops_note}")
    agent_html = "".join(f'<div class="action-item">{_esc(item)}</div>' for item in agent_items[:6])

    audit_text = (
        f"✅ 推荐方案「{rec_label}」已基于搜索结果生成；"
        f"共 {len(options)} 套可比方案供挑选。"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(route)} 差旅行程方案</title>
<style>
*{{box-sizing:border-box;}}
body{{
  font-family:"PingFang SC","Hiragino Sans GB","Noto Sans SC","Microsoft YaHei",sans-serif;
  background:#fff;color:#1e293b;margin:0;padding:0;line-height:1.5;
}}
.card{{
  background:#fff;border:1px solid #e2e8f0;border-radius:12px;
  box-shadow:0 4px 14px rgba(15,23,42,.06);padding:0;margin-bottom:16px;
}}
.card.recommended{{background:#fff;}}
.header .title-group h1{{font-size:22px;margin:0 0 6px;}}
.header .meta{{font-size:14px;color:#64748b;margin:0;}}
.section-title{{font-size:18px;font-weight:700;margin:0 0 12px;}}
.recommend-reason{{
  border-left:4px solid #3b82f6;background:#f8fafc;
  padding:10px 14px;margin:0 0 12px;border-radius:0 8px 8px 0;
}}
.weather-box{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 16px;}}
.weather-item{{
  background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
  padding:12px 16px;font-size:14px;
}}
.audit-conclusion{{
  background:#eff6ff;border:1px solid #bfdbfe;color:#2563eb;font-weight:600;
  padding:10px 14px;border-radius:8px;margin:0 0 16px;font-size:14px;
}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{background:#f8fafc;color:#475569;font-weight:600;text-align:left;padding:8px 10px;border-bottom:1px solid #e2e8f0;}}
td{{padding:8px 10px;border-bottom:1px solid #e2e8f0;vertical-align:top;}}
.total-row td{{font-weight:700;}}
.price{{color:#dc2626;font-weight:700;}}
.comparison-table{{display:block;overflow-x:auto;white-space:nowrap;font-size:13px;}}
.comparison-table table{{min-width:720px;}}
.plan-item{{border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin-bottom:10px;background:#f8fafc;}}
.plan-item.recommended{{background:#eff6ff;border-color:#bfdbfe;color:#2563eb;font-weight:600;}}
.plan-item ul{{margin:8px 0;padding-left:18px;}}
.badge{{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;}}
.badge-success{{background:#dbeafe;color:#2563eb;}}
.plan-note.success{{background:#eff6ff;color:#2563eb;padding:8px 10px;border-radius:6px;font-size:13px;}}
.agent-actions{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;}}
.action-item{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;font-size:13px;}}
.next-steps{{
  background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px 16px;
}}
.next-steps li{{margin:6px 0;}}
.muted{{color:#64748b;}}
@media (max-width:768px){{
  .card{{padding:0;}}
  .header .meta{{display:block;margin-top:4px;}}
  .weather-box{{grid-template-columns:1fr;}}
  .agent-actions{{grid-template-columns:1fr;}}
}}
</style>
</head>
<body>
<div class="card header">
  <div class="title-group">
    <h1>🗂️ 差旅行程方案（{_esc(route)}）</h1>
    <p class="meta">{_esc(" · ".join(meta_bits) if meta_bits else "出行约束未提供")}</p>
  </div>
</div>

<div class="card recommended">
  <h2 class="section-title">🏆 推荐方案 · {_esc(rec_label)}</h2>
  {f'<div class="recommend-reason"><strong>为什么是它</strong>：{_esc(rec_reason)}</div>' if rec_reason else ''}
  {weather_html}
  <table>
    <thead><tr><th>环节</th><th>详情</th><th>费用</th></tr></thead>
    <tbody>{cost_rows or '<tr><td colspan="3" class="muted">暂无明细</td></tr>'}</tbody>
  </table>
</div>

<div class="audit-conclusion">{_esc(audit_text)}</div>

<div class="card">
  <h2 class="section-title">📋 方案对比（需要挑选时看这里）</h2>
  <div class="comparison-table">
    <table>
      <thead>
        <tr>
          <th>方案</th><th>标签</th><th>去程交通</th><th>返程交通</th>
          <th>酒店(房型)</th><th>总耗时</th><th>总价</th><th>评分</th><th>审核</th>
        </tr>
      </thead>
      <tbody>{cmp_rows or '<tr><td colspan="9" class="muted">无对比数据</td></tr>'}</tbody>
    </table>
  </div>
</div>

<div class="card">
  <h2 class="section-title">🔍 方案明细（想核对细节时展开）</h2>
  {detail_blocks or '<p class="muted">暂无方案明细</p>'}
</div>

<div class="card next-steps">
  <h2 class="section-title">👉 下一步</h2>
  <ul>
    <li><strong>确认方案</strong>：告诉我你选哪套方案（如「确认方案1」），我再进入预订流程。</li>
    <li><strong>想调整</strong>：告诉我新的条件（换日期 / 指定航司 / 舱位等），我按新条件重新规划。</li>
  </ul>
</div>

<div class="card">
  <h2 class="section-title">🧭 Agent 为你做了什么</h2>
  <div class="agent-actions">{agent_html}</div>
</div>
</body>
</html>"""
