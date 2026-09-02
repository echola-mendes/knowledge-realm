"""往返空结果时退化为单程；方案页不输出 params JSON。"""
from __future__ import annotations

from app.travel import tools as travel_tools


def test_search_flights_tool_roundtrip_empty_falls_back_one_way(monkeypatch):
    calls = []

    def fake_search(**kw):
        calls.append(kw)
        if kw.get("back_date"):
            return {"itemList": [], "message": "智慧交通结果为空", "status": 1}
        return {
            "itemList": [{"flightNo": "MU5109", "price": 620}],
            "message": "success",
            "status": 0,
        }

    monkeypatch.setattr(travel_tools.flyai, "search_flights", fake_search)
    out = travel_tools.search_flights_tool(
        {
            "origin": "上海",
            "destination": "北京",
            "depart_date": "2026-09-08",
            "return_date": "2026-09-10",
            "cabin": "经济舱",
        }
    )
    assert len(calls) == 2
    assert calls[0]["back_date"] == "2026-09-10"
    assert calls[1]["back_date"] is None
    assert out["roundtripFallback"] == "one_way"
    assert out["itemList"][0]["flightNo"] == "MU5109"
    assert "单程" in out["systemMessage"]


def test_render_plan_html_params_not_json():
    plan = {
        "options": [{"id": "opt-1", "label": "方案 1", "segments": [{"summary": "MU5109 虹桥T2→首都T2"}], "total_price": 620, "notes": ""}],
        "comparison": [],
        "recommendation": {"option_id": "opt-1", "reason": "首个"},
        "total_price_summary": "最低总价约 620",
    }
    html = travel_tools.render_plan_html(
        plan,
        {"itemList": [{"flightNo": "MU5109", "price": 620}]},
        None,
        {"origin": "上海", "destination": "北京", "depart_date": "2026-09-08", "cabin": "经济舱"},
    )
    assert "上海 → 北京" in html
    assert "2026-09-08" in html
    assert '{"origin"' not in html
    assert "MU5109" in html
