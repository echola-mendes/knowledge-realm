import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, load_settings
from app import main as main_mod
from app.config import reset_settings


def test_missing_database_url_raises():
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_settings(environ={}, load_file=False)


def test_invalid_embedding_dim_raises():
    env = {"DATABASE_URL": "postgresql+psycopg://postgres@127.0.0.1:5432/echola_kb", "EMBEDDING_DIM": "0"}
    with pytest.raises(ConfigError, match="EMBEDDING_DIM"):
        load_settings(environ=env, load_file=False)


def test_settings_without_llm_key():
    env = {"DATABASE_URL": "postgresql+psycopg://postgres@127.0.0.1:5432/echola_kb"}
    s = load_settings(environ=env, load_file=False)
    assert s.ai_configured is False
    assert s.host == "127.0.0.1"
    assert s.embedding_dim == 1024


def test_health_without_llm_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/echola_kb")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    reset_settings()
    app = main_mod.create_app(load_file=False, ensure_default=False)
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["ai_configured"] is False
    assert body["host"] == "127.0.0.1"
    reset_settings()
