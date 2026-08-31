from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from app.config import get_settings
from app.main import reset_app_state

TEST_DB_NAME = "echola_kb_test"
_SERVER_DIR = Path(__file__).resolve().parents[1]


def _render(url) -> str:
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def isolate_from_user_database(tmp_path_factory):
    reset_app_state()
    prod = get_settings(load_file=True)
    prod_url = make_url(prod.database_url)
    test_url = _render(prod_url.set(database=TEST_DB_NAME))
    admin_url = _render(prod_url.set(database="postgres"))
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": TEST_DB_NAME},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        engine.dispose()
    data_dir = tmp_path_factory.mktemp("data")
    os.environ["DATABASE_URL"] = test_url
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["ELASTICSEARCH_URL"] = "http://127.0.0.1:9200"
    os.environ["SESSION_SECRET"] = "pytest-session-secret-min-32-chars"
    os.environ["INITIAL_USERNAME"] = "echola"
    os.environ["INITIAL_PASSWORD"] = "pytest-isolated-password"
    reset_app_state()
    alembic_cli = _SERVER_DIR / ".venv" / "bin" / "alembic"
    subprocess.run(
        [sys.executable, str(alembic_cli), "upgrade", "head"],
        cwd=str(_SERVER_DIR),
        check=True,
    )
    loaded = make_url(get_settings(load_file=True).database_url).database
    if loaded != TEST_DB_NAME:
        raise RuntimeError(f"pytest refused to use user database {loaded!r}")
    from app.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE message, conversation, document_tag, favorite, "
                "document_chunk, entity_link, retrieval_label, rag_eval_case, user_memory, user_chunk_setting, document, entity, tag, knowledge_base, users CASCADE"
            )
        )
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations"):
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": table},
            ).scalar()
            if exists:
                conn.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
    yield
    reset_app_state()


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    def fake(texts: list[str]) -> list[list[float]]:
        dim = get_settings().embedding_dim
        return [[0.01] * dim for _ in texts]

    monkeypatch.setattr("app.index.embed_texts", fake)


@pytest.fixture(autouse=True)
def fake_elasticsearch(monkeypatch):
    from app.es_bm25 import MemoryChunkIndex

    monkeypatch.setattr("app.es_bm25._override", MemoryChunkIndex())
    monkeypatch.setattr("app.es_bm25._elastic", None)


@pytest.fixture(autouse=True)
def skip_post_index_enrich(monkeypatch):
    monkeypatch.setattr("app.index._enrich_after_index", lambda _document_id: None)


@pytest.fixture(autouse=True)
def skip_rerank(monkeypatch):
    monkeypatch.setattr("app.search.score_documents", lambda query, documents: None)
