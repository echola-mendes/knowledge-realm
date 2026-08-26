import inspect
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.index import index_document
from app.main import create_app, reset_app_state
from app.parse import parse_text_document
import app.search as search_mod


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


def _directional_embed(texts: list[str]) -> list[list[float]]:
    dim = get_settings().embedding_dim
    vectors = []
    for text in texts:
        vec = [0.0] * dim
        if "苹果" in text:
            vec[0] = 1.0
        elif "橙子" in text:
            vec[1] = 1.0
        else:
            vec[2] = 1.0
        vectors.append(vec)
    return vectors


def test_keyword_hit_enters_rrf_and_kb_isolation(monkeypatch):
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    monkeypatch.setattr("app.search.embed_texts", _directional_embed)
    monkeypatch.setattr("app.index.embed_texts", _directional_embed)
    with _client() as client:
        kb_a = client.post("/api/knowledge-bases", json={"name": f"库A-{uuid.uuid4().hex[:8]}"}).json()
        kb_b = client.post("/api/knowledge-bases", json={"name": f"库B-{uuid.uuid4().hex[:8]}"}).json()
        client.post(
            "/api/documents/notes",
            json={"content": "文档讲苹果", "filename": "apple.md", "knowledge_base_id": kb_a["id"]},
        )
        rare = client.post(
            "/api/documents/notes",
            json={
                "content": "独角兽代号XYZ出现在此段",
                "filename": "rare.md",
                "knowledge_base_id": kb_a["id"],
            },
        )
        other = client.post(
            "/api/documents/notes",
            json={
                "content": "独角兽代号XYZ只在B库",
                "filename": "leak.md",
                "knowledge_base_id": kb_b["id"],
            },
        )
        parse_text_document(uuid.UUID(rare.json()["id"]))
        parse_text_document(uuid.UUID(other.json()["id"]))
        apple = client.post(
            "/api/documents/notes",
            json={"content": "另一篇也讲水果", "filename": "fruit.md", "knowledge_base_id": kb_a["id"]},
        )
        parse_text_document(uuid.UUID(apple.json()["id"]))
        for row in (rare, other, apple):
            index_document(uuid.UUID(row.json()["id"]))

        hits = client.post(
            "/api/search",
            json={"query": "独角兽代号XYZ", "knowledge_base_id": kb_a["id"]},
        )
        assert hits.status_code == 200
        names = [h["document_name"] for h in hits.json()]
        assert "rare.md" in names
        assert "leak.md" not in names


def test_search_without_elasticsearch_url_is_visible(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
    monkeypatch.setenv("ELASTICSEARCH_URL", "")
    reset_app_state()
    monkeypatch.setattr("app.index.embedding_keys_ready", lambda: True)
    with TestClient(create_app(load_file=True, ensure_default=True)) as client:
        res = client.post("/api/search", json={"query": "苹果"})
        assert res.status_code == 503
        assert "ELASTICSEARCH_URL" in res.json()["detail"]
    reset_app_state()


def test_search_module_has_no_second_vector_or_trgm():
    src = inspect.getsource(search_mod)
    assert "pg_trgm" not in src
    assert "trgm" not in src
    assert src.count("cosine_distance") <= 2
