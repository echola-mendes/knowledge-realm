import inspect

from app.p1 import tools
from app.p1.tools import search_knowledge


def test_search_knowledge_wraps_search_chunks_not_http(monkeypatch):
    src = inspect.getsource(tools)
    assert "langgraph" not in src.lower()
    assert "/api/search" not in src
    assert "httpx" not in src
    assert "search_chunks" in src
    called: dict = {}

    def fake_search(session, query, **kwargs):
        called["session"] = session
        called["query"] = query
        called["kwargs"] = kwargs
        return []

    monkeypatch.setattr("app.p1.tools.search_chunks", fake_search)
    marker = object()
    hits = search_knowledge(marker, "苹果", knowledge_base_id=None, k=5)
    assert hits == []
    assert called["session"] is marker
    assert called["query"] == "苹果"
    assert called["kwargs"]["k"] == 5
