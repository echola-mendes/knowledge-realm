import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    def fake(texts: list[str]) -> list[list[float]]:
        dim = get_settings().embedding_dim
        return [[0.01] * dim for _ in texts]

    monkeypatch.setattr("app.index.embed_texts", fake)
