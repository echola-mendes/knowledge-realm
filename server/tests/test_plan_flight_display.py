"""plan 展示：FlyAI journeys 嵌套字段必须抽出可读航班，不能只出 —。"""
from __future__ import annotations

import json

from app.travel import tools as travel_tools

FLYAI_NESTED = {
    "success": True,
    "itemList": [
        {
            "adultPrice": "¥620.0",
            "journeys": [
                {
                    "journeyType": "直达",
                    "segments": [
                        {
                            "depStationShortName": "虹桥",
                            "depTerm": "T2",
                            "depDateTime": "2026-09-08 08:00:00",
                            "arrStationShortName": "首都",
                            "arrTerm": "T2",
                            "arrDateTime": "2026-09-08 10:20:00",
                            "marketingTransportName": "东航",
                            "marketingTransportNo": "MU5109",
                            "seatClassName": "经济舱",
                        }
                    ],
                }
            ],
        }
    ],
}


def test_fallback_plan_reads_flyai_journeys(monkeypatch):
    monkeypatch.setattr(travel_tools, "_plan_llm", lambda payload: None)
    plan = travel_tools.plan_itinerary(FLYAI_NESTED, None, {"cabin": "经济舱"})
    summary = plan["options"][0]["segments"][0]["summary"]
    assert "MU5109" in summary
    assert "虹桥T2" in summary
    assert "08:00" in summary
    assert plan["options"][0]["total_price"] == "620.0"


def test_normalize_plan_fills_segment_summary_from_fields():
    parsed = {
        "options": [
            {
                "id": "a",
                "label": "早班",
                "segments": [
                    {
                        "type": "flight",
                        "flightNo": "MU5109",
                        "depTime": "08:00",
                        "arrTime": "10:20",
                        "depAirport": "虹桥T2",
                        "arrAirport": "首都T2",
                        "price": 620,
                    }
                ],
                "total_price": 620,
            }
        ],
        "comparison": [],
        "recommendation": {"option_id": "a", "reason": "早班"},
        "total_price_summary": "620",
    }
    plan = travel_tools._normalize_plan(parsed)
    assert plan is not None
    assert "MU5109" in plan["options"][0]["segments"][0]["summary"]
    assert "虹桥T2" in plan["options"][0]["segments"][0]["summary"]
    dims = {d["dimension"]: d["rows"][0]["value"] for d in plan["comparison"]}
    assert "总价" in dims
    assert str(dims["总价"]) == "620"
    assert "MU5109" in str(dims.get("航班") or dims.get("行程") or "")


def test_plan_llm_payload_uses_flat_flights(monkeypatch):
    captured: dict[str, str] = {}

    def fake(payload: str):
        captured["payload"] = payload
        return None

    monkeypatch.setattr(travel_tools, "_plan_llm", fake)
    travel_tools.plan_itinerary(FLYAI_NESTED, None, {"cabin": "经济舱"})
    data = json.loads(captured["payload"])
    assert data["flights"][0]["flight_no"] == "MU5109"
    assert "journeys" not in captured["payload"]


def test_plan_itinerary_hollow_llm_falls_back_to_flyai(monkeypatch):
    monkeypatch.setattr(
        travel_tools,
        "_plan_llm",
        lambda payload: {
            "options": [{"id": "a", "label": "空", "segments": [{"summary": "暂无航班"}], "total_price": None}],
            "comparison": [],
            "recommendation": {"option_id": "a", "reason": "未搜到符合条件航班"},
            "total_price_summary": "",
        },
    )
    plan = travel_tools.plan_itinerary(FLYAI_NESTED, None, {})
    assert "MU5109" in plan["options"][0]["segments"][0]["summary"]
    dims = {d["dimension"]: [str(r.get("value")) for r in d["rows"]] for d in plan["comparison"]}
    assert "620.0" in dims["总价"]
    assert any("MU5109" in v for v in dims.get("航班", []))
    assert plan["options"][0]["total_price"] == "620.0"
    assert plan["recommendation"]["option_id"] == "opt-1"


def test_render_plan_html_comparison_uses_labels_not_opt_ids():
    plan = travel_tools._fallback_plan(FLYAI_NESTED, None, {})
    html = travel_tools.render_plan_html(
        plan, FLYAI_NESTED, None, {"origin": "上海", "destination": "北京"}
    )
    assert "方案对比" in html
    assert "MU5109" in html
    assert "<th>opt-1</th>" not in html
    assert "总价" in html
    assert "航班" in html


def test_plan_itinerary_empty_segments_falls_back(monkeypatch):
    monkeypatch.setattr(
        travel_tools,
        "_plan_llm",
        lambda payload: {
            "options": [{"id": "a", "label": "空", "segments": [], "total_price": None}],
            "recommendation": {"option_id": "a", "reason": "无"},
            "total_price_summary": "",
        },
    )
    plan = travel_tools.plan_itinerary(FLYAI_NESTED, None, {})
    assert "MU5109" in plan["options"][0]["segments"][0]["summary"]


def test_render_plan_html_shows_recommended_flight():
    plan = travel_tools._fallback_plan(FLYAI_NESTED, None, {})
    html = travel_tools.render_plan_html(
        plan, FLYAI_NESTED, None, {"origin": "上海", "destination": "北京"}
    )
    assert "MU5109" in html
    assert "虹桥T2" in html
    assert "<code>" not in html
