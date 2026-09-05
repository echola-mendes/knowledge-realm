import inspect
import uuid

from sqlalchemy import select

from app.db import session_scope
from app.main import reset_app_state
from app.models import User
from app.agent import graph as graph_mod
from app.agent.ltm import write_user_memory
import app.rag.search as search_mod


def _client():
    reset_app_state()
    from app.config import get_settings
    from http_client import api_client

    get_settings(load_file=True)
    return api_client()


def test_ltm_survives_new_conversation(monkeypatch):
    monkeypatch.setattr("app.routers.master.llm_keys_ready", lambda: True)
    monkeypatch.setattr(graph_mod, "reason_decide", lambda state: {"next_action": "generate"})
    chat_calls: list[dict] = []

    def fake_chat(question, context, history=None, *, summary=None, ltm=None):
        chat_calls.append({"question": question, "ltm": list(ltm or [])})
        return "ok"

    monkeypatch.setattr("app.llm.chat", fake_chat)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"LTM-{uuid.uuid4().hex[:8]}"}).json()
        session = session_scope()
        try:
            user = session.scalar(select(User).limit(1))
            assert user is not None
            write_user_memory(session, user.id, "preference", "回答要简洁")
            session.commit()
        finally:
            session.close()
        first = client.post(
            "/api/agent",
            json={"task": "agent", "query": "你好", "knowledge_base_id": kb["id"]},
        )
        assert first.status_code == 200, first.text
        cid1 = first.json()["conversation_id"]
        assert chat_calls[0]["ltm"] == [{"id": chat_calls[0]["ltm"][0]["id"], "kind": "preference", "content": "回答要简洁"}]
        second = client.post(
            "/api/agent",
            json={"task": "agent", "query": "再聊聊", "knowledge_base_id": kb["id"]},
        )
        assert second.status_code == 200, second.text
        cid2 = second.json()["conversation_id"]
        assert cid1 != cid2
        assert chat_calls[1]["ltm"][0]["content"] == "回答要简洁"
    reset_app_state()


def test_search_module_does_not_use_user_memory():
    src = inspect.getsource(search_mod)
    assert "user_memory" not in src
    assert "UserMemory" not in src
