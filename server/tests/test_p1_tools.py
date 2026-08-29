import inspect
import uuid

from app.p1 import tools
from app.p1.tools import search_knowledge, web_search


def test_search_knowledge_wraps_search_chunks_not_http(monkeypatch):
    src = inspect.getsource(tools)
    assert "langgraph" not in src.lower()
    assert "/api/search" not in src
    assert "playwright" not in src.lower()
    assert "web_search" in src
    sk = inspect.getsource(search_knowledge)
    assert "httpx" not in sk
    assert "search_chunks" in sk
    called: dict = {}

    def fake_search(session, query, **kwargs):
        called["session"] = session
        called["query"] = query
        called["kwargs"] = kwargs
        return []

    monkeypatch.setattr("app.p1.tools.search_chunks", fake_search)
    marker = object()
    uid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    hits = search_knowledge(marker, "苹果", user_id=uid, knowledge_base_id=None, k=5)
    assert hits == []
    assert called["session"] is marker
    assert called["query"] == "苹果"
    assert called["kwargs"]["k"] == 5


def test_web_search_posts_httpx(monkeypatch):
    class FakeSettings:
        web_search_url = "https://search.example/q"
        web_search_api_key = "sk-test"
        web_search_timeout = 10

    posted: dict = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"title": "T", "url": "https://e", "snippet": "S"}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        posted["url"] = url
        posted["json"] = json
        posted["headers"] = headers
        posted["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr("app.p1.tools.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.p1.tools.httpx.post", fake_post)
    hits = web_search("苹果")
    assert hits == [{"title": "T", "url": "https://e", "snippet": "S"}]
    assert posted["url"] == "https://search.example/q"
    assert posted["json"] == {"query": "苹果"}
    assert posted["headers"]["Authorization"] == "Bearer sk-test"
    assert posted["timeout"] == 10.0


def test_web_search_skips_http_when_unconfigured(monkeypatch):
    class FakeSettings:
        web_search_url = ""
        web_search_api_key = ""
        web_search_timeout = 10

    def boom(*args, **kwargs):
        raise AssertionError("unconfigured web_search must not call httpx")

    monkeypatch.setattr("app.p1.tools.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.p1.tools.httpx.post", boom)
    assert web_search("苹果") == []
