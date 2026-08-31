from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.insights import analyze_conflicts, analyze_gaps
from app.main import create_app, reset_app_state
from app.models import Document, User
from app.passwords import hash_password
from http_client import TEST_PASSWORD, api_client

CHAIN_JSON = json.dumps(
    {
        "conflicts": [
            {
                "documents": ["a.md", "b.md"],
                "point": "退款周期矛盾",
                "detail": "A 说 7 天，B 说 15 天",
                "suggestion": "统一为 7 天",
            }
        ]
    },
    ensure_ascii=False,
)


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def test_analyze_conflicts_parses_mock_chain(monkeypatch):
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights._chat_complete", lambda system, human: CHAIN_JSON)
    docs = [
        SimpleNamespace(filename="a.md", summary="退款 7 天"),
        SimpleNamespace(filename="b.md", summary="退款 15 天"),
    ]
    out = analyze_conflicts(docs)
    assert out["truncated"] is False
    assert out["conflicts"][0]["point"] == "退款周期矛盾"
    assert out["conflicts"][0]["documents"] == ["a.md", "b.md"]


def test_analyze_conflicts_truncates_over_30(monkeypatch):
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    captured: dict[str, str] = {}

    def fake(system: str, human: str) -> str:
        captured["human"] = human
        return '{"conflicts":[]}'

    monkeypatch.setattr("app.insights._chat_complete", fake)
    docs = [SimpleNamespace(filename=f"d{i}.md", summary=f"s{i}") for i in range(35)]
    out = analyze_conflicts(docs)
    assert out["truncated"] is True
    assert captured["human"].count("文档名：") == 30
    assert "d30.md" not in captured["human"]


def test_conflicts_endpoint_returns_mock(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights._chat_complete", lambda system, human: CHAIN_JSON)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"冲突-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]
        session = session_scope()
        try:
            session.add(
                Document(
                    knowledge_base_id=uuid.UUID(kb_id),
                    filename="a.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary="退款 7 天",
                )
            )
            session.commit()
        finally:
            session.close()
        res = client.post(f"/api/knowledge-bases/{kb_id}/insights/conflicts")
        assert res.status_code == 200
        data = res.json()
        assert data["truncated"] is False
        assert data["conflicts"][0]["point"] == "退款周期矛盾"
        assert data["conflicts"][0]["documents"] == ["a.md", "b.md"]
    reset_app_state()


def test_conflicts_cross_user_404(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"隔离-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]

    other_name = f"o-{uuid.uuid4().hex[:10]}"
    session = session_scope()
    try:
        session.add(User(username=other_name, password_hash=hash_password(TEST_PASSWORD)))
        session.commit()
    finally:
        session.close()

    other = TestClient(create_app(load_file=True, ensure_default=False))
    login = other.post("/api/auth/login", json={"username": other_name, "password": TEST_PASSWORD})
    assert login.status_code == 200
    res = other.post(f"/api/knowledge-bases/{kb_id}/insights/conflicts")
    assert res.status_code == 404
    reset_app_state()


def test_conflicts_no_llm_key(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: False)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"无Key-{uuid.uuid4().hex[:8]}"})
        kb_id = kb.json()["id"]
        res = client.post(f"/api/knowledge-bases/{kb_id}/insights/conflicts")
        assert res.status_code == 503
    reset_app_state()

def test_analyze_conflicts_invokes_without_template_error(monkeypatch):
    """System prompt JSON must not go through ChatPromptTemplate f-string parsing."""
    import app.insights as mod

    monkeypatch.setattr(mod, "llm_keys_ready", lambda: True)
    captured: dict[str, object] = {}

    class FakeModel:
        def invoke(self, messages):
            captured["messages"] = messages
            from types import SimpleNamespace
            return SimpleNamespace(content='{"conflicts":[]}')

    monkeypatch.setattr("langchain_openai.ChatOpenAI", lambda **kw: FakeModel())
    docs = [SimpleNamespace(filename="a.md", summary="x")]
    assert mod.analyze_conflicts(docs)["conflicts"] == []
    assert captured["messages"][0].content.find("conflicts") >= 0



GAP_JSON = json.dumps(
    {
        "covered_topics": ["退款政策"],
        "gaps": [
            {
                "topic": "发票开具",
                "evidence": "如何开发票",
                "suggestion": "补充发票流程文档",
            }
        ],
    },
    ensure_ascii=False,
)


def test_analyze_gaps_parses_mock_chain(monkeypatch):
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights._chat_complete", lambda system, human: GAP_JSON)
    docs = [SimpleNamespace(filename="a.md", summary="退款 7 天")]
    out = analyze_gaps(docs, ["如何开发票"])
    assert out["truncated"] is False
    assert out["covered_topics"] == ["退款政策"]
    assert out["gaps"][0]["topic"] == "发票开具"
    assert out["gaps"][0]["evidence"] == "如何开发票"


def test_analyze_gaps_omits_evidence_without_labels(monkeypatch):
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    captured: dict[str, str] = {}

    def fake(system: str, human: str) -> str:
        captured["human"] = human
        return json.dumps(
            {
                "covered_topics": ["退款政策"],
                "gaps": [{"topic": "发票", "evidence": "模型编造的佐证", "suggestion": "补文档"}],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.insights._chat_complete", fake)
    docs = [SimpleNamespace(filename="a.md", summary="退款 7 天")]
    out = analyze_gaps(docs, [])
    assert "【低命中提问】" not in captured["human"]
    assert out["gaps"][0]["topic"] == "发票"
    assert out["gaps"][0]["evidence"] == ""


def test_gaps_endpoint_returns_mock(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights._chat_complete", lambda system, human: GAP_JSON)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"缺口-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]
        session = session_scope()
        try:
            session.add(
                Document(
                    knowledge_base_id=uuid.UUID(kb_id),
                    filename="a.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary="退款 7 天",
                )
            )
            session.commit()
        finally:
            session.close()
        res = client.post(f"/api/knowledge-bases/{kb_id}/insights/gaps")
        assert res.status_code == 200
        data = res.json()
        assert data["truncated"] is False
        assert data["covered_topics"] == ["退款政策"]
        assert data["gaps"][0]["topic"] == "发票开具"
        # 无 retrieval_label 时省略佐证
        assert data["gaps"][0]["evidence"] == ""
    reset_app_state()


def test_gaps_cross_user_404(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"缺口隔离-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]

    other_name = f"g-{uuid.uuid4().hex[:10]}"
    session = session_scope()
    try:
        session.add(User(username=other_name, password_hash=hash_password(TEST_PASSWORD)))
        session.commit()
    finally:
        session.close()

    other = TestClient(create_app(load_file=True, ensure_default=False))
    login = other.post("/api/auth/login", json={"username": other_name, "password": TEST_PASSWORD})
    assert login.status_code == 200
    res = other.post(f"/api/knowledge-bases/{kb_id}/insights/gaps")
    assert res.status_code == 404
    reset_app_state()


def test_organize_apply_tags_writes_and_is_idempotent(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.p1.chains.suggest_tag_names", lambda text: ["标签甲", "标签乙"])
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"整理-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]
        session = session_scope()
        try:
            session.add(
                Document(
                    knowledge_base_id=uuid.UUID(kb_id),
                    filename="a.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary="退款 7 天",
                )
            )
            session.commit()
        finally:
            session.close()
        res = client.post(f"/api/knowledge-bases/{kb_id}/insights/organize")
        assert res.status_code == 200
        data = res.json()
        assert data["applied_tags"] is True
        assert len(data["applied"]) == 1
        assert data["applied"][0]["tags"] == ["标签甲", "标签乙"]
        # idempotent: second call should not re-apply
        res2 = client.post(f"/api/knowledge-bases/{kb_id}/insights/organize")
        assert res2.status_code == 200
        assert res2.json()["applied"] == []
    reset_app_state()


def test_organize_dry_run_does_not_write_tags(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.p1.chains.suggest_tag_names", lambda text: ["标签甲"])
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"整理预览-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]
        session = session_scope()
        try:
            session.add(
                Document(
                    knowledge_base_id=uuid.UUID(kb_id),
                    filename="x.md",
                    ext=".md",
                    kind="note",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary="内容",
                )
            )
            session.commit()
        finally:
            session.close()
        res = client.post(f"/api/knowledge-bases/{kb_id}/insights/organize", json={"apply_tags": False})
        assert res.status_code == 200
        data = res.json()
        assert data["applied_tags"] is False
        assert len(data["applied"]) == 1
        # no tags actually persisted
        res2 = client.post(f"/api/knowledge-bases/{kb_id}/insights/organize")
        assert res2.json()["applied"][0]["tags"] == ["标签甲"]
    reset_app_state()


def test_organize_reports_duplicates_and_empty_summary(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.insights.llm_keys_ready", lambda: True)
    monkeypatch.setattr("app.p1.chains.suggest_tag_names", lambda text: [])
    with _client() as client:
        kb1 = client.post("/api/knowledge-bases", json={"name": f"整理报告1-{uuid.uuid4().hex[:8]}"})
        assert kb1.status_code == 201
        kb1_id = kb1.json()["id"]
        kb2 = client.post("/api/knowledge-bases", json={"name": f"整理报告2-{uuid.uuid4().hex[:8]}"})
        assert kb2.status_code == 201
        kb2_id = kb2.json()["id"]
        session = session_scope()
        try:
            session.add_all([
                Document(
                    knowledge_base_id=uuid.UUID(kb1_id),
                    filename="a.md",
                    ext=".md",
                    kind="note",
                    checksum="cross-ck",
                    status="ready",
                    byte_size=1,
                    summary="摘要",
                ),
                Document(
                    knowledge_base_id=uuid.UUID(kb2_id),
                    filename="a.md",
                    ext=".md",
                    kind="file",
                    checksum="cross-ck",
                    status="ready",
                    byte_size=1,
                    summary="",
                ),
                Document(
                    knowledge_base_id=uuid.UUID(kb1_id),
                    filename="a.txt",
                    ext=".txt",
                    kind="file",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary="",
                ),
                Document(
                    knowledge_base_id=uuid.UUID(kb1_id),
                    filename="x.md",
                    ext=".md",
                    kind="file",
                    checksum=uuid.uuid4().hex,
                    status="ready",
                    byte_size=1,
                    summary="ok",
                ),
            ])
            session.commit()
        finally:
            session.close()
        res = client.post(f"/api/knowledge-bases/{kb1_id}/insights/organize")
        assert res.status_code == 200
        data = res.json()
        # cross-kb same checksum
        assert any("a.md" in group for group in data["duplicates"])
        # same base name within kb
        assert any("a.md" in group and "a.txt" in group for group in data["duplicates"])
        assert "a.txt" in data["empty_summary"]
        assert "x.md" not in data["empty_summary"]
        assert "x.md" in data["bad_names"]
    reset_app_state()


def test_organize_cross_user_404(monkeypatch):
    monkeypatch.setattr("app.routers.insights.llm_keys_ready", lambda: True)
    with _client() as client:
        kb = client.post("/api/knowledge-bases", json={"name": f"整理隔离-{uuid.uuid4().hex[:8]}"})
        assert kb.status_code == 201
        kb_id = kb.json()["id"]

    other_name = f"o-{uuid.uuid4().hex[:10]}"
    session = session_scope()
    try:
        session.add(User(username=other_name, password_hash=hash_password(TEST_PASSWORD)))
        session.commit()
    finally:
        session.close()

    other = TestClient(create_app(load_file=True, ensure_default=False))
    login = other.post("/api/auth/login", json={"username": other_name, "password": TEST_PASSWORD})
    assert login.status_code == 200
    res = other.post(f"/api/knowledge-bases/{kb_id}/insights/organize")
    assert res.status_code == 404
    reset_app_state()
