"""方案页出发地/目的地天气出行提醒。"""
from __future__ import annotations

from app.travel import tools as travel_tools
from app.travel import weather as weather_mod

WTTR_SHANGHAI = {
    "current_condition": [{"temp_C": "30", "weatherDesc": [{"value": "多云"}]}],
    "weather": [
        {
            "date": "2026-09-08",
            "mintempC": "28",
            "maxtempC": "35",
            "hourly": [
                {"time": "1200", "weatherDesc": [{"value": "多云"}]},
            ],
        }
    ],
}

WTTR_BEIJING = {
    "current_condition": [{"temp_C": "24", "weatherDesc": [{"value": "小雨"}]}],
    "weather": [
        {
            "date": "2026-09-08",
            "mintempC": "22",
            "maxtempC": "28",
            "hourly": [
                {"time": "1200", "weatherDesc": [{"value": "小雨"}]},
            ],
        }
    ],
}

SAMPLE_WEATHER = {
    "origin": {
        "city": "上海",
        "description": "多云",
        "min_temp": "28",
        "max_temp": "35",
        "hint": "适合出行",
    },
    "destination": {
        "city": "北京",
        "description": "小雨",
        "min_temp": "22",
        "max_temp": "28",
        "hint": "建议携带雨具",
    },
    "advice": "出发地天气良好适合飞行，目的地有降水建议携带雨具，户外活动安排在间隙",
}

FLIGHTS = {
    "success": True,
    "itemList": [
        {"flightNo": "MU5101", "price": 400, "depTime": "08:00", "arrTime": "10:30"},
    ],
}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_render_plan_html_shows_origin_and_dest_weather():
    plan = travel_tools._fallback_plan(FLIGHTS, None, {})
    html = travel_tools.render_plan_html(
        plan,
        FLIGHTS,
        None,
        {"origin": "上海", "destination": "北京"},
        weather=SAMPLE_WEATHER,
    )
    assert "weather-box" in html
    assert "出发地 · 上海" in html
    assert "目的地 · 北京" in html
    assert "多云" in html
    assert "小雨" in html
    assert "天气提醒" in html
    assert "携带雨具" in html
    assert "环境感知" in html


def test_render_plan_html_omits_weather_when_missing():
    plan = travel_tools._fallback_plan(FLIGHTS, None, {})
    html = travel_tools.render_plan_html(
        plan, FLIGHTS, None, {"origin": "上海", "destination": "北京"}
    )
    assert 'class="weather-box"' not in html
    assert "天气提醒" not in html
    assert "环境感知" not in html


def test_fetch_city_weather_parses_wttr(monkeypatch):
    monkeypatch.setattr(weather_mod.httpx, "get", lambda *a, **k: _Resp(WTTR_SHANGHAI))
    out = weather_mod.fetch_city_weather("上海", "2026-09-08")
    assert out is not None
    assert out["city"] == "上海"
    assert out["description"] == "多云"
    assert out["min_temp"] == "28"
    assert out["max_temp"] == "35"
    assert out["hint"] == "适合出行"


def test_fetch_city_weather_wet_hint(monkeypatch):
    monkeypatch.setattr(weather_mod.httpx, "get", lambda *a, **k: _Resp(WTTR_BEIJING))
    out = weather_mod.fetch_city_weather("北京", "2026-09-08")
    assert out is not None
    assert out["description"] == "小雨"
    assert out["hint"] == "建议携带雨具"


def test_fetch_city_weather_none_on_error(monkeypatch):
    def boom(*a, **k):
        raise weather_mod.httpx.ConnectError("down")

    monkeypatch.setattr(weather_mod.httpx, "get", boom)
    assert weather_mod.fetch_city_weather("上海") is None


def test_fetch_trip_weather_parallel(monkeypatch):
    def fake_get(url, **kwargs):
        if "北京" in url or "%E5%8C%97%E4%BA%AC" in url:
            return _Resp(WTTR_BEIJING)
        return _Resp(WTTR_SHANGHAI)

    monkeypatch.setattr(weather_mod.httpx, "get", fake_get)
    out = weather_mod.fetch_trip_weather("上海", "北京", "2026-09-08", "2026-09-10")
    assert out["origin"]["city"] == "上海"
    assert out["destination"]["city"] == "北京"
    assert "适合飞行" in out["advice"]
    assert "携带雨具" in out["advice"]


def test_save_plan_html_includes_fetched_weather(monkeypatch):
    monkeypatch.setattr(travel_tools.minio_store, "minio_ready", lambda: False)
    monkeypatch.setattr(weather_mod, "fetch_trip_weather", lambda *a, **k: SAMPLE_WEATHER)
    plan = travel_tools._fallback_plan(FLIGHTS, None, {"cabin": "经济舱"})
    out = travel_tools.save_plan_html(
        plan,
        FLIGHTS,
        None,
        {"origin": "上海", "destination": "北京", "depart_date": "2026-09-08"},
        "c",
    )
    assert "weather-box" in out["html"]
    assert "出发地 · 上海" in out["html"]
    assert "目的地 · 北京" in out["html"]
    assert "天气提醒" in out["html"]
