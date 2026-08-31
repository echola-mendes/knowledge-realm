from __future__ import annotations

import uuid

from app import index as index_mod
from app.db import session_scope
from app.models import Document, DocumentChunk
from sqlalchemy import select
from tests.http_client import api_client


def _client():
    from app.main import reset_app_state
    from app.config import get_settings

    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _make_ready_doc(client, md_text: str) -> str:
    """上传笔记并全量索引完成，返回 document_id。"""
    kb = client.post("/api/knowledge-bases", json={"name": f"Inc-{uuid.uuid4().hex[:8]}"}).json()
    doc = client.post(
        "/api/documents/notes",
        json={"knowledge_base_id": kb["id"], "content": md_text},
    ).json()
    with session_scope() as session:
        doc_orm = session.get(Document, uuid.UUID(doc["id"]))
        from app.storage import parsed_dir

        parsed_dir(doc_orm.id).mkdir(parents=True, exist_ok=True)
        parsed_dir(doc_orm.id).joinpath("document.md").write_text(md_text, encoding="utf-8")
        session.commit()
    index_mod.index_document(uuid.UUID(doc["id"]))
    return doc["id"]


def _chunks_of(doc_id: str) -> list[DocumentChunk]:
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == uuid.UUID(doc_id))
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )
        session.expunge_all()
        return rows


def test_incremental_reuses_unchanged_embeddings(monkeypatch):
    with _client() as client:
        doc_id = _make_ready_doc(client, "# 甲\n第一段内容保持不变\n\n# 乙\n第二段内容保持不变")
    before = _chunks_of(doc_id)
    assert len(before) >= 2

    from app.storage import parsed_dir

    parsed_dir(uuid.UUID(doc_id)).joinpath("document.md").write_text(
        "# 甲\n第一段内容保持不变\n\n# 乙\n第二段内容已更新", encoding="utf-8"
    )
    calls: list[list[str]] = []
    original = index_mod._embed_all

    def spy(texts):
        calls.append(list(texts))
        return original(texts)

    monkeypatch.setattr(index_mod, "_embed_all", spy)
    result = index_mod.index_document_incremental(uuid.UUID(doc_id))
    assert result == "ready"
    # 只重嵌变更的 1 条
    assert len(calls) == 1 and len(calls[0]) == 1 and "第二段内容已更新" in calls[0][0]
    after = _chunks_of(doc_id)
    # 未变更切片向量复用（同一对象内容一致），变更切片来自 spy 的真实重嵌
    unchanged = next(r for r in after if "第一段内容保持不变" in r.content)
    old_unchanged = next(r for r in before if "第一段内容保持不变" in r.content)
    assert list(unchanged.embedding) == list(old_unchanged.embedding)
    assert next(r for r in after if "第二段内容已更新" in r.content) is not None


def test_incremental_unchanged_when_content_identical(monkeypatch):
    with _client() as client:
        doc_id = _make_ready_doc(client, "# 标题\n固定内容")
    calls: list[list[str]] = []
    monkeypatch.setattr(index_mod, "_embed_all", lambda texts: calls.append(list(texts)) or [])
    result = index_mod.index_document_incremental(uuid.UUID(doc_id))
    assert result == "unchanged"
    assert calls == []


def test_incremental_only_embeds_new_chunks(monkeypatch):
    with _client() as client:
        doc_id = _make_ready_doc(client, "# A\n旧内容不动")
    from app.storage import parsed_dir

    parsed_dir(uuid.UUID(doc_id)).joinpath("document.md").write_text(
        "# A\n旧内容不动\n\n# B\n全新追加的段落", encoding="utf-8"
    )
    calls: list[list[str]] = []
    original = index_mod._embed_all

    def spy(texts):
        calls.append(list(texts))
        return original(texts)

    monkeypatch.setattr(index_mod, "_embed_all", spy)
    result = index_mod.index_document_incremental(uuid.UUID(doc_id))
    assert result == "ready"
    assert len(calls) == 1 and len(calls[0]) == 1 and "全新追加的段落" in calls[0][0]
    after = _chunks_of(doc_id)
    assert {r.content for r in after} == {"# A\n旧内容不动", "# B\n全新追加的段落"}
