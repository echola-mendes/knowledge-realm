"""plan 工具与 itinerary_plan_agent 流程测试。"""
from __future__ import annotations

import json
import uuid

from app import plan_agent as plan_mod
from app.travel import tools as travel_tools

FLIGHTS = {
    "success": True,
    "itemList": [
        {"flightNo": "MU5101", "price": 400, "depTime": "08:00", "arrTime": "10:30"},
        {"flightNo": "CA1856", "price": 520, "depTime": "14:00", "arrTime": "16:25"},
        {"flightNo": "HU7602", "price": 455, "depTime": "19:00", "arrTime": "21:20"},
    ],
}


# ---------- travel tools ----------


def test_flights_tool_passthrough(monkeypatch):
    monkeypatch.setattr(travel_tools.flyai, "search_flights", lambda **kw: FLIGHTS)
    out = travel_tools.search_flights_tool({"origin": "上海", "destination": "北京", "depart_date": "2026-09-10"})
    assert out["itemList"] == FLIGHTS["itemList"]


def test_flights_tool_error_shape(monkeypatch):
    def boom(**kw):
        raise travel_tools.flyai.FlyaiError("cli 未安装")

    monkeypatch.setattr(travel_tools.flyai, "search_flights", boom)
    out = travel_tools.search_flights_tool({"origin": "上海", "destination": "北京", "depart_date": "2026-09-10"})
    assert out["kind"] == "error"
    assert "cli 未安装" in out["message"]


def test_hotels_placeholder_when_not_configured(monkeypatch):
    monkeypatch.setattr(travel_tools, "hotel_source_enabled", lambda: False)
    out = travel_tools.search_hotels_tool({"destination": "北京", "depart_date": "2026-09-10", "return_date": "2026-09-12"})
    assert out["kind"] == "placeholder"
    assert "未配置" in out["message"]
    # 不伪造房型：占位结构里没有任何房型字段
    assert not any(k for k in out if k not in ("kind", "message"))


def test_plan_itinerary_llm_output_normalized():
    parsed = {
        "options": [
            {"id": "a", "label": "早班", "segments": [{"summary": "MU5101"}], "total_price": 400, "notes": ""},
            {"id": "b", "label": "下午", "segments": [], "total_price": 520},
        ],
        "comparison": [{"dimension": "总价", "rows": [{"option_id": "a", "value": 400}, {"option_id": "b", "value": 520}]}],
        "recommendation": {"option_id": "a", "reason": "最便宜"},
        "total_price_summary": "最低 400",
    }
    plan = travel_tools._normalize_plan(parsed)
    assert plan is not None
    assert plan["recommendation"]["option_id"] == "a"
    assert plan["comparison"][0]["rows"][0]["value"] == 400
    assert plan["total_price_summary"] == "最低 400"


def test_plan_itinerary_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(travel_tools, "_plan_llm", lambda payload: None)
    plan = travel_tools.plan_itinerary(FLIGHTS, travel_tools.HOTEL_PLACEHOLDER, {"cabin": "经济舱"})
    for key in ("options", "comparison", "recommendation", "total_price_summary"):
        assert key in plan
    assert len(plan["options"]) >= 2
    assert plan["recommendation"]["option_id"] == "opt-1"


def test_plan_itinerary_invalid_llm_falls_back(monkeypatch):
    monkeypatch.setattr(travel_tools, "_plan_llm", lambda payload: {"options": []})
    plan = travel_tools.plan_itinerary(FLIGHTS, None, {})
    assert plan["options"], "结构不合法时应回退兜底而非空方案"


def test_save_plan_html_key_and_note(monkeypatch):
    uploaded: dict = {}

    def fake_put(convo, html):
        uploaded["convo"] = convo
        uploaded["html"] = html
        return {"key": f"plans/{convo}/x.html", "url": "http://minio/plans/x.html", "bucket": "zhiyu"}

    monkeypatch.setattr(travel_tools.minio_store, "minio_ready", lambda: True)
    monkeypatch.setattr(travel_tools.minio_store, "put_plan_html", fake_put)
    plan = travel_tools._fallback_plan(FLIGHTS, None, {"cabin": "经济舱"})
    out = travel_tools.save_plan_html(
        plan,
        FLIGHTS,
        None,
        {"cabin": "经济舱"},
        "convo-9",
    )
    assert uploaded["convo"] == "convo-9"
    assert "推荐" in uploaded["html"] and "MU5101" in uploaded["html"]
    assert out["url"] == "http://minio/plans/x.html"
    assert "回看" in out["note"]


def test_save_plan_html_unconfigured_minio(monkeypatch):
    monkeypatch.setattr(travel_tools.minio_store, "minio_ready", lambda: False)
    out = travel_tools.save_plan_html({"options": []}, None, None, {}, "c")
    assert out["url"] is None
    assert "未配置" in out["note"]


# ---------- plan agent 流程 ----------


def _config(emit):
    return {"configurable": {"emit": emit}}


def test_plan_agent_asks_when_required_fields_missing(monkeypatch):
    # 无 LLM：启发式抽不出要素 → ask
    monkeypatch.setattr(plan_mod, "_reason_llm", lambda state: None)
    events: list[dict] = []
    out = plan_mod.build_plan_graph().invoke(
        plan_mod.plan_initial_state("帮我规划行程"), config=_config(events.append)
    )
    assert out["answer"].startswith("为给出可比方案")
    assert "出发地" in out["answer"] and "出发日期" in out["answer"]





def test_has_plan_oral_signal_prd_acceptance():
    from app.travel.params_parse import has_plan_oral_signal
    import datetime as dt

    ref = dt.date(2026, 9, 1)
    assert has_plan_oral_signal("下周二去上海，周四返回", ref=ref)
    assert has_plan_oral_signal("下周二上海出发去北京，周四返回", ref=ref)
    assert not has_plan_oral_signal("什么是RAG", ref=ref)
    assert not has_plan_oral_signal("上海到杭州坐高铁", ref=ref)


def test_parse_travel_params_natural_sentence():
    from app.travel.params_parse import parse_travel_params

    ref = __import__("datetime").date(2026, 9, 1)  # 周二
    params = parse_travel_params("下周二上海出发去北京，周四返回，经济舱", ref=ref)
    assert params["origin"] == "上海"
    assert params["destination"] == "北京"
    assert params["depart_date"] == "2026-09-08"
    assert params["return_date"] == "2026-09-10"
    assert params["cabin"] == "经济舱"


def test_reason_decide_heuristic_when_llm_returns_empty(monkeypatch):
    monkeypatch.setattr(plan_mod, "_reason_llm", lambda state: {"params": {}, "action": "ask"})
    state = plan_mod.plan_initial_state("下周二上海出发去北京，周四返回，经济舱")
    updates = plan_mod.reason_decide(state)
    assert updates["next_action"] == "flights"
    assert updates["params"]["origin"] == "上海"
    assert updates["params"]["destination"] == "北京"
    assert updates["params"]["depart_date"] == "2026-09-08"


def test_plan_agent_full_flow_search_plan_save(monkeypatch):
    decisions = iter(
        [
            {"params": {"origin": "上海", "destination": "北京", "depart_date": "2026-09-10", "cabin": "经济舱"}, "action": "flights"},
            {"action": "plan"},
            {"action": "save"},
            {"action": "direct"},
        ]
    )
    monkeypatch.setattr(plan_mod, "_reason_llm", lambda state: next(decisions))
    monkeypatch.setattr(plan_mod.travel_tools, "search_flights_tool", lambda params: FLIGHTS)
    monkeypatch.setattr(
        plan_mod.travel_tools,
        "search_hotels_tool",
        lambda params: (_ for _ in ()).throw(AssertionError("本轮未请求酒店")),
    )
    monkeypatch.setattr(
        plan_mod.travel_tools,
        "plan_itinerary",
        lambda f, h, p: {"options": [{"id": "opt-1", "label": "方案 1", "segments": [], "total_price": 400, "notes": ""}], "comparison": [], "recommendation": {"option_id": "opt-1", "reason": "低价"}, "total_price_summary": "最低 400"},
    )
    monkeypatch.setattr(
        plan_mod.travel_tools,
        "save_plan_html",
        lambda plan, f, h, p, convo: {"html": "<html></html>", "url": "http://minio/p.html", "key": "plans/c/1.html", "note": "已存 MinIO"},
    )
    monkeypatch.setattr(
        "app.llm.chat",
        lambda question, context, history=None, *, summary=None, ltm=None: "推荐 opt-1：最便宜，总价 400。",
    )
    events: list[dict] = []
    out = plan_mod.build_plan_graph().invoke(
        plan_mod.plan_initial_state("下周二去北京，经济舱", conversation_id="convo-flow"),
        config=_config(events.append),
    )
    assert out["answer"].startswith("方案已生成，请查看下方完整方案展示")
    assert len(out["travel_data"]["flights"]) == 3
    assert out["plan_html"]["url"] == "http://minio/p.html"
    # 事件顺序：progress → travel_data → … → plan_html，均先于 answer
    types = [e["type"] for e in events]
    assert types[0] == "progress"
    assert "travel_data" in types and "plan_html" in types
    assert types.index("travel_data") < types.index("plan_html")
    assert any("3 条" in e.get("text", "") for e in events if e["type"] == "progress")


def test_plan_agent_finalize_survives_llm_connection_error(monkeypatch):
    """搜票/方案已成功时，finalize 的 LLM 断连不得把整次 Agent 打成 500。"""
    monkeypatch.setattr(plan_mod, "_reason_llm", lambda state: None)
    monkeypatch.setattr(plan_mod.travel_tools, "search_flights_tool", lambda params: FLIGHTS)
    monkeypatch.setattr(
        plan_mod.travel_tools,
        "plan_itinerary",
        lambda f, h, p: {
            "options": [{"id": "opt-1", "label": "方案 1", "segments": [], "total_price": 400, "notes": ""}],
            "comparison": [],
            "recommendation": {"option_id": "opt-1", "reason": "低价"},
            "total_price_summary": "最低 400",
        },
    )
    monkeypatch.setattr(
        plan_mod.travel_tools,
        "save_plan_html",
        lambda plan, f, h, p, convo: {
            "html": "<html></html>",
            "url": None,
            "key": None,
            "note": "MinIO 未配置：方案页仅本次会话实时展示。",
        },
    )

    def boom(*_a, **_k):
        raise ConnectionError("Connection refused")

    monkeypatch.setattr("app.llm.chat", boom)
    plan_mod.reset_plan_graph()
    out = plan_mod.build_plan_graph().invoke(
        plan_mod.plan_initial_state("下周二上海出发去北京，周四返回，经济舱"),
        config=_config(lambda e: None),
    )
    assert out["answer"]
    assert "推荐" in out["answer"] or "方案" in out["answer"]
    assert "方案已生成" in out["answer"]


def test_plan_agent_keeps_params_across_preference_change(monkeypatch):
    """改偏好不丢日期/城市：params merge 保留旧字段（图无状态，由 reason_decide 合并语义保证）。"""
    monkeypatch.setattr(
        plan_mod,
        "_reason_llm",
        lambda state: {"params": {"cabin": "公务舱"}, "action": "flights"},
    )
    state = plan_mod.plan_initial_state("改公务舱")
    state["params"] = {"origin": "上海", "destination": "北京", "depart_date": "2026-09-10"}
    state["flights_raw"] = FLIGHTS
    updates = plan_mod.reason_decide(state)
    assert updates["params"]["cabin"] == "公务舱"
    assert updates["params"]["origin"] == "上海"
    assert updates["params"]["depart_date"] == "2026-09-10"

def test_is_plan_revision_query_date_change():
    from datetime import date

    from app.travel.params_parse import is_plan_revision_query

    ref = date(2026, 9, 5)
    assert is_plan_revision_query("换成下周三出发", ref=ref)
    assert is_plan_revision_query("改成公务舱", ref=ref)
    assert not is_plan_revision_query("什么是RAG", ref=ref)


def test_reason_decide_forces_pipeline_when_llm_says_direct_on_date_change(monkeypatch):
    """改日期追问：LLM 误选 direct 时仍强制 flights→plan→save。"""
    monkeypatch.setattr(
        plan_mod,
        "_reason_llm",
        lambda state: {
            "params": {"depart_date": "2026-09-09"},
            "action": "direct",
        },
    )
    state = plan_mod.plan_initial_state(
        "换成下周三出发",
        history=[
            {"role": "user", "content": "下周二深圳出发去北京，周四返回，经济舱"},
            {"role": "assistant", "content": "方案已生成，请查看下方完整方案展示。"},
        ],
    )
    updates = plan_mod.reason_decide(state)
    assert updates["params"]["origin"] == "深圳"
    assert updates["params"]["destination"] == "北京"
    assert updates["params"]["depart_date"] == "2026-09-09"
    assert updates["next_action"] == "flights"


def test_reason_decide_forces_save_after_plan_when_llm_says_direct(monkeypatch):
    monkeypatch.setattr(plan_mod, "_reason_llm", lambda state: {"action": "direct"})
    state = plan_mod.plan_initial_state("换成下周三出发")
    state["params"] = {
        "origin": "深圳",
        "destination": "北京",
        "depart_date": "2026-09-09",
        "return_date": "2026-09-10",
        "cabin": "经济舱",
    }
    state["flights_raw"] = FLIGHTS
    state["plan"] = {"options": [{"id": "opt-1"}], "recommendation": {"option_id": "opt-1", "reason": "x"}}
    updates = plan_mod.reason_decide(state)
    assert updates["next_action"] == "save"

