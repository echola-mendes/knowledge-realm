"""flyai CLI 封装测试：itemList 原样透传、参数拼装、失败路径。"""
from __future__ import annotations

import json
import subprocess

import pytest

from app.travel import flyai


def _ok_proc(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["flyai"], returncode=0, stdout=json.dumps(payload, ensure_ascii=False), stderr=""
    )


SAMPLE = {
    "success": True,
    "itemList": [
        {"flightNo": "MU5101", "depCity": "上海", "arrCity": "北京", "price": 400},
        {"flightNo": "CA1856", "depCity": "上海", "arrCity": "北京", "price": 520},
    ],
}


def test_search_flights_passthrough_item_list(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return _ok_proc(SAMPLE)

    monkeypatch.setattr(flyai.subprocess, "run", fake_run)
    out = flyai.search_flights(origin="上海", destination="北京", dep_date="2026-09-10")
    assert out["itemList"] == SAMPLE["itemList"]
    argv = calls[0]
    assert argv[0] == "flyai"
    assert argv[1] == "search-flight"
    joined = " ".join(argv)
    assert "--origin 上海" in joined
    assert "--destination 北京" in joined
    assert "--dep-date 2026-09-10" in joined
    assert "--journey-type" not in joined
    assert "--adult-count" not in joined


def test_search_flights_round_trip_args(monkeypatch):
    captured = {}

    def spy(args, **kw):
        captured["argv"] = args
        return _ok_proc(SAMPLE)

    monkeypatch.setattr(flyai.subprocess, "run", spy)
    flyai.search_flights(
        origin="上海", destination="北京", dep_date="2026-09-10", back_date="2026-09-12", seat_class="经济舱"
    )
    joined = " ".join(captured["argv"])
    assert "--back-date 2026-09-12" in joined
    assert "--seat-class-name 经济舱" in joined
    assert "--journey-type" not in joined
    assert "--adult-count" not in joined


def test_search_flights_nested_data_item_list(monkeypatch):
    wrapped = {
        "data": {"itemList": SAMPLE["itemList"]},
        "message": "success",
        "status": 0,
        "systemMessage": "trial",
    }

    monkeypatch.setattr(flyai.subprocess, "run", lambda args, **kw: _ok_proc(wrapped))
    out = flyai.search_flights(origin="上海", destination="北京", dep_date="2026-09-10")
    assert out["itemList"] == SAMPLE["itemList"]
    assert out["message"] == "success"
    assert out["systemMessage"] == "trial"


def test_search_flights_missing_params_raises(monkeypatch):
    with pytest.raises(flyai.FlyaiError):
        flyai.search_flights(origin="", destination="北京", dep_date="2026-09-10")


def test_search_flights_cli_failure(monkeypatch):
    proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="quota exceeded")
    monkeypatch.setattr(flyai.subprocess, "run", lambda args, **kw: proc)
    with pytest.raises(flyai.FlyaiError, match="quota exceeded"):
        flyai.search_flights(origin="上海", destination="北京", dep_date="2026-09-10")


def test_search_flights_unparseable_output(monkeypatch):
    proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr="")
    monkeypatch.setattr(flyai.subprocess, "run", lambda args, **kw: proc)
    with pytest.raises(flyai.FlyaiError, match="不可解析"):
        flyai.search_flights(origin="上海", destination="北京", dep_date="2026-09-10")


def test_search_hotels_requires_dates(monkeypatch):
    with pytest.raises(flyai.FlyaiError):
        flyai.search_hotels(dest_name="杭州", check_in_date="", check_out_date="2026-09-12")
