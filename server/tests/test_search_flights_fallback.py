"""往返空结果时退化为去程+返程分别搜索；方案页不输出 params JSON。"""
from __future__ import annotations

from app.travel import tools as travel_tools


def test_search_flights_tool_roundtrip_empty_falls_back_split(monkeypatch):
    calls = []

    def fake_search(**kw):
        calls.append(kw)
        if kw.get("back_date"):
            return {"itemList": [], "message": "智慧交通结果为空", "status": 1}
        if kw.get("origin") == "北京" and kw.get("destination") == "上海":
            return {
                "itemList": [{"flightNo": "CA8341", "adultPrice": "¥580.0", "price": 580}],
                "message": "success",
                "status": 0,
            }
        return {
            "itemList": [{"flightNo": "MU5109", "adultPrice": "¥620.0", "price": 620}],
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
    assert len(calls) == 3
    assert calls[0]["back_date"] == "2026-09-10"
    assert calls[1]["back_date"] is None and calls[1]["origin"] == "上海"
    assert calls[2]["origin"] == "北京" and calls[2]["destination"] == "上海"
    assert out["roundtripFallback"] == "split_one_way"
    assert out["itemList"][0]["flightNo"] == "MU5109"
    assert out["returnItemList"][0]["flightNo"] == "CA8341"


def test_fallback_plan_combines_outbound_return():
    raw = {
        "itemList": [
            {
                "adultPrice": "¥620.0",
                "journeys": [
                    {
                        "segments": [
                            {
                                "marketingTransportNo": "MU5109",
                                "depStationShortName": "虹桥",
                                "depTerm": "T2",
                                "depDateTime": "2026-09-08 08:00:00",
                                "arrStationShortName": "首都",
                                "arrTerm": "T2",
                                "arrDateTime": "2026-09-08 10:20:00",
                            }
                        ]
                    }
                ],
            }
        ],
        "returnItemList": [
            {
                "adultPrice": "¥580.0",
                "journeys": [
                    {
                        "segments": [
                            {
                                "marketingTransportNo": "CA8341",
                                "depStationShortName": "首都",
                                "depTerm": "T2",
                                "depDateTime": "2026-09-10 20:00:00",
                                "arrStationShortName": "虹桥",
                                "arrTerm": "T2",
                                "arrDateTime": "2026-09-10 22:15:00",
                            }
                        ]
                    }
                ],
            }
        ],
    }
    plan = travel_tools._fallback_plan(raw, None, {})
    assert len(plan["options"]) == 1
    assert len(plan["options"][0]["segments"]) == 2
    assert "MU5109" in plan["options"][0]["segments"][0]["summary"]
    assert "CA8341" in plan["options"][0]["segments"][1]["summary"]
    assert plan["options"][0]["total_price"] == "1200.0"


def test_extract_price_from_nested_price_dict():
    item = {"price": {"adultPrice": "¥499.5"}, "journeys": []}
    assert travel_tools._extract_price(item) == "499.5"


def test_dedupe_flight_items():
    items = [
        {"flightNo": "CZ8886", "depTime": "19:45", "depAirport": "虹桥T2", "arrAirport": "大兴", "price": 100},
        {"flightNo": "CZ8886", "depTime": "19:45", "depAirport": "虹桥T2", "arrAirport": "大兴", "price": 100},
        {"flightNo": "MF2634", "depTime": "19:45", "depAirport": "虹桥T2", "arrAirport": "大兴", "price": 110},
    ]
    out = travel_tools._dedupe_flight_items(items)
    assert len(out) == 2


def test_remap_comparison_fixes_llm_option_ids():
    options = [
        {"id": "opt-1", "label": "CZ8886 19:45", "segments": [{"summary": "a"}], "total_price": "620"},
        {"id": "opt-2", "label": "MF2634 19:45", "segments": [{"summary": "b"}], "total_price": "630"},
    ]
    broken = [
        {
            "dimension": "航班",
            "rows": [
                {"option_id": "CZ8886 19:45 / MF2634 19:45", "value": "CZ8886"},
                {"option_id": "CZ8886 19:45 / MF2634 19:45", "value": "MF2634"},
            ],
        }
    ]
    fixed = travel_tools._remap_comparison(broken, options)
    assert fixed[0]["rows"][0]["option_id"] == "opt-1"
    assert fixed[0]["rows"][1]["option_id"] == "opt-2"


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


def test_fallback_plan_native_roundtrip_item_two_journeys():
    """联程 itemList 含去程+返程 journeys 时，应拆成两段。"""
    raw = {
        "itemList": [
            {
                "adultPrice": "¥1200.0",
                "journeys": [
                    {
                        "segments": [
                            {
                                "marketingTransportNo": "MU5109",
                                "depStationShortName": "虹桥",
                                "depTerm": "T2",
                                "depDateTime": "2026-09-08 08:00:00",
                                "arrStationShortName": "首都",
                                "arrTerm": "T2",
                                "arrDateTime": "2026-09-08 10:20:00",
                            }
                        ]
                    },
                    {
                        "segments": [
                            {
                                "marketingTransportNo": "CA8341",
                                "depStationShortName": "首都",
                                "depTerm": "T2",
                                "depDateTime": "2026-09-10 20:00:00",
                                "arrStationShortName": "虹桥",
                                "arrTerm": "T2",
                                "arrDateTime": "2026-09-10 22:15:00",
                            }
                        ]
                    },
                ],
            }
        ],
    }
    plan = travel_tools._fallback_plan(raw, None, {"return_date": "2026-09-10"})
    assert len(plan["options"][0]["segments"]) == 2
    assert plan["options"][0]["segments"][0].get("leg") == "outbound"
    assert plan["options"][0]["segments"][1].get("leg") == "return"
    assert "CA8341" in plan["options"][0]["segments"][1]["summary"]


def test_plan_itinerary_llm_outbound_only_gets_return_attached(monkeypatch):
    monkeypatch.setattr(
        travel_tools,
        "_plan_llm",
        lambda payload: {
            "options": [
                {
                    "id": "opt-1",
                    "label": "早班",
                    "segments": [{"type": "flight", "summary": "MU5109 虹桥T2→首都T2 08:00", "price": "620"}],
                    "total_price": "620",
                    "notes": "",
                }
            ],
            "comparison": [],
            "recommendation": {"option_id": "opt-1", "reason": "早班"},
            "total_price_summary": "620",
        },
    )
    raw = {
        "itemList": [
            {
                "adultPrice": "¥620.0",
                "journeys": [
                    {
                        "segments": [
                            {
                                "marketingTransportNo": "MU5109",
                                "depStationShortName": "虹桥",
                                "depTerm": "T2",
                                "depDateTime": "2026-09-08 08:00:00",
                                "arrStationShortName": "首都",
                                "arrTerm": "T2",
                                "arrDateTime": "2026-09-08 10:20:00",
                            }
                        ]
                    }
                ],
            }
        ],
        "returnItemList": [
            {
                "adultPrice": "¥580.0",
                "journeys": [
                    {
                        "segments": [
                            {
                                "marketingTransportNo": "CA8341",
                                "depStationShortName": "首都",
                                "depTerm": "T2",
                                "depDateTime": "2026-09-10 20:00:00",
                                "arrStationShortName": "虹桥",
                                "arrTerm": "T2",
                                "arrDateTime": "2026-09-10 22:15:00",
                            }
                        ]
                    }
                ],
            }
        ],
    }
    plan = travel_tools.plan_itinerary(raw, None, {"return_date": "2026-09-10"})
    assert len(plan["options"][0]["segments"]) == 2
    assert "CA8341" in plan["options"][0]["segments"][1]["summary"]
    html = travel_tools.render_plan_html(plan, raw, None, {"origin": "上海", "destination": "北京", "return_date": "2026-09-10"})
    assert "🛬 返程" in html
    assert "CA8341" in html
