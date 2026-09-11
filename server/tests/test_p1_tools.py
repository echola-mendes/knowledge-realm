import inspect
import uuid

from app.agent import tools
from app.agent.tools import search_knowledge, tools_for, web_search


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

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)
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

    monkeypatch.setattr("app.agent.tools.web.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.agent.tools.web.httpx.post", fake_post)
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

    monkeypatch.setattr("app.agent.tools.web.get_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.agent.tools.web.httpx.post", boom)
    assert web_search("苹果") == []


def test_tools_for_gating():
    names_off = {t.name for t in tools_for(allow_web=False, enable_graph=False)}
    assert "web_search" not in names_off
    assert "search_graph" not in names_off
    assert "search_knowledge" in names_off
    assert "text2sql" in names_off

    names_on = {t.name for t in tools_for(allow_web=True, enable_graph=True)}
    assert "web_search" in names_on
    assert "search_graph" in names_on


def test_tool_schema_excludes_runtime_fields():
    forbidden = {"session", "user_id", "conversation_id", "knowledge_base_id", "config"}
    for t in tools_for(allow_web=True, enable_graph=True):
        props = set((t.args_schema.model_json_schema().get("properties") or {}).keys())
        assert not (props & forbidden), f"{t.name} schema has runtime fields: {props & forbidden}"


def test_tool_descriptions_cover_usage_timing():
    """Step 2: descriptions encode purpose + when to use / retry / switch."""
    from app.agent.tools.registry import AGENT_TOOLS

    by_name = {t.name: t for t in AGENT_TOOLS}
    required = {
        "search_knowledge": ("知识库", "改写"),
        "search_graph": ("实体", "关系"),
        "web_search": ("联网", "不足"),
        "text2sql": ("结构化",),
    }
    for name, needles in required.items():
        desc_raw = by_name[name].description or ""
        for needle in needles:
            assert needle in desc_raw, f"{name} description missing {needle!r}: {desc_raw}"
    forbidden = {"session", "user_id", "conversation_id", "knowledge_base_id", "config"}
    for name in required:
        props = set((by_name[name].args_schema.model_json_schema().get("properties") or {}).keys())
        assert not (props & forbidden)
