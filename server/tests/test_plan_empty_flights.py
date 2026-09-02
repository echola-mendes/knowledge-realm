"""plan agent: empty flyai results should not re-search or fabricate empty plan pages."""
from __future__ import annotations

from app import plan_agent as plan_mod


def test_plan_agent_does_not_research_flights_after_empty_result(monkeypatch):
    calls = {"n": 0}

    def fake_search(params):
        calls["n"] += 1
        return {"itemList": [], "message": "智慧交通结果为空", "status": 1}

    monkeypatch.setattr(plan_mod, "_reason_llm", lambda state: None)
    monkeypatch.setattr(plan_mod.travel_tools, "search_flights_tool", fake_search)

    def boom_plan(*_a, **_k):
        raise AssertionError("empty flights must not call plan_itinerary")

    def boom_save(*_a, **_k):
        raise AssertionError("empty flights must not call save_plan_html")

    monkeypatch.setattr(plan_mod.travel_tools, "plan_itinerary", boom_plan)
    monkeypatch.setattr(plan_mod.travel_tools, "save_plan_html", boom_save)
    plan_mod.reset_plan_graph()
    out = plan_mod.build_plan_graph().invoke(
        plan_mod.plan_initial_state("下周二上海出发去北京，周四返回，经济舱"),
        config={"configurable": {"emit": lambda e: None}},
    )
    assert calls["n"] == 1
    assert out.get("flights_raw") is not None
    assert not out.get("plan")
    assert not out.get("plan_html")
    assert "未搜到" in out["answer"] or "暂未能" in out["answer"]
