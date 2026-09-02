"""Integration probe for live flyai CLI (skip in CI)."""
from __future__ import annotations

import datetime as dt

import pytest

from app.travel import flyai
from app.travel.params_parse import parse_travel_params


@pytest.mark.integration
def test_live_flyai_shanghai_beijing_roundtrip():
    text = "下周二上海出发去北京，周四返回，经济舱"
    ref = dt.date(2026, 9, 1)
    params = parse_travel_params(text, ref=ref)
    assert params["origin"] == "上海"
    assert params["destination"] == "北京"
    out = flyai.search_flights(
        origin=params["origin"],
        destination=params["destination"],
        dep_date=params["depart_date"],
        back_date=params.get("return_date"),
        seat_class=params.get("cabin"),
    )
    items = out.get("itemList") or []
    assert isinstance(items, list)
    assert len(items) > 0
