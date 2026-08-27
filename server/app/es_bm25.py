from __future__ import annotations

from collections.abc import Sequence
import uuid
from typing import Protocol

from app.config import get_settings

INDEX_NAME = "echola_document_chunk"


class EsNotConfiguredError(Exception):
    pass


class ChunkIndex(Protocol):
    def upsert(
        self,
        *,
        chunk_id: uuid.UUID,
        content: str,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: str,
    ) -> None: ...

    def delete_document(self, document_id: uuid.UUID) -> None: ...

    def delete_knowledge_base(self, knowledge_base_id: uuid.UUID) -> None: ...

    def search(
        self,
        query: str,
        *,
        knowledge_base_ids: Sequence[uuid.UUID],
        k: int,
        kind: str | None = None,
        document_id: uuid.UUID | None = None,
        document_ids: frozenset[uuid.UUID] | None = None,
    ) -> list[tuple[uuid.UUID, float]]: ...


class MemoryChunkIndex:
    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def upsert(
        self,
        *,
        chunk_id: uuid.UUID,
        content: str,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: str,
    ) -> None:
        self._docs[str(chunk_id)] = {
            "content": content,
            "knowledge_base_id": str(knowledge_base_id),
            "document_id": str(document_id),
            "kind": kind,
            "chunk_id": str(chunk_id),
        }

    def delete_document(self, document_id: uuid.UUID) -> None:
        did = str(document_id)
        self._docs = {k: v for k, v in self._docs.items() if v["document_id"] != did}

    def delete_knowledge_base(self, knowledge_base_id: uuid.UUID) -> None:
        kid = str(knowledge_base_id)
        self._docs = {k: v for k, v in self._docs.items() if v["knowledge_base_id"] != kid}

    def search(
        self,
        query: str,
        *,
        knowledge_base_ids: Sequence[uuid.UUID],
        k: int,
        kind: str | None = None,
        document_id: uuid.UUID | None = None,
        document_ids: frozenset[uuid.UUID] | None = None,
    ) -> list[uuid.UUID]:
        if not knowledge_base_ids:
            return []
        if document_ids is not None and not document_ids:
            return []
        allowed_kb = {str(i) for i in knowledge_base_ids}
        allowed = {str(i) for i in document_ids} if document_ids is not None else None
        scored: list[tuple[float, str]] = []
        q = query.strip()
        for item in self._docs.values():
            if item["knowledge_base_id"] not in allowed_kb:
                continue
            if kind is not None and item["kind"] != kind:
                continue
            if document_id is not None and item["document_id"] != str(document_id):
                continue
            if allowed is not None and item["document_id"] not in allowed:
                continue
            score = float(item["content"].count(q)) if q else 0.0
            if score <= 0:
                continue
            scored.append((score, item["chunk_id"]))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [(uuid.UUID(cid), score) for score, cid in scored[:k]]


class ElasticChunkIndex:
    def __init__(self, url: str) -> None:
        from elasticsearch import Elasticsearch

        self._client = Elasticsearch(url, request_timeout=30)
        self._ensured = False

    def _index_exists(self) -> bool:
        return bool(self._client.indices.exists(index=INDEX_NAME))

    def _ensure(self) -> None:
        if self._ensured:
            return
        if not self._index_exists():
            self._client.indices.create(
                index=INDEX_NAME,
                settings={"number_of_shards": 1, "number_of_replicas": 0},
                mappings={
                    "properties": {
                        "content": {"type": "text"},
                        "knowledge_base_id": {"type": "keyword"},
                        "document_id": {"type": "keyword"},
                        "kind": {"type": "keyword"},
                        "chunk_id": {"type": "keyword"},
                    }
                },
            )
        self._ensured = True

    def upsert(
        self,
        *,
        chunk_id: uuid.UUID,
        content: str,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        kind: str,
    ) -> None:
        self._ensure()
        self._client.index(
            index=INDEX_NAME,
            id=str(chunk_id),
            document={
                "content": content,
                "knowledge_base_id": str(knowledge_base_id),
                "document_id": str(document_id),
                "kind": kind,
                "chunk_id": str(chunk_id),
            },
            refresh=True,
        )

    def delete_document(self, document_id: uuid.UUID) -> None:
        if not self._index_exists():
            return
        self._client.delete_by_query(
            index=INDEX_NAME,
            query={"term": {"document_id": str(document_id)}},
            refresh=True,
            ignore_unavailable=True,
        )

    def delete_knowledge_base(self, knowledge_base_id: uuid.UUID) -> None:
        if not self._index_exists():
            return
        self._client.delete_by_query(
            index=INDEX_NAME,
            query={"term": {"knowledge_base_id": str(knowledge_base_id)}},
            refresh=True,
            ignore_unavailable=True,
        )

    def search(
        self,
        query: str,
        *,
        knowledge_base_ids: Sequence[uuid.UUID],
        k: int,
        kind: str | None = None,
        document_id: uuid.UUID | None = None,
        document_ids: frozenset[uuid.UUID] | None = None,
    ) -> list[uuid.UUID]:
        if not knowledge_base_ids:
            return []
        if document_ids is not None and not document_ids:
            return []
        self._ensure()
        filters: list[dict] = [{"terms": {"knowledge_base_id": [str(i) for i in knowledge_base_ids]}}]
        if kind is not None:
            filters.append({"term": {"kind": kind}})
        if document_id is not None:
            filters.append({"term": {"document_id": str(document_id)}})
        if document_ids is not None:
            filters.append({"terms": {"document_id": [str(i) for i in document_ids]}})
        resp = self._client.search(
            index=INDEX_NAME,
            size=k,
            query={
                "bool": {
                    "must": [{"match": {"content": query}}],
                    "filter": filters,
                }
            },
        )
        rows: list[tuple[uuid.UUID, float]] = []
        for hit in resp["hits"]["hits"]:
            rows.append((uuid.UUID(hit["_id"]), float(hit.get("_score") or 0.0)))
        return rows


_override: ChunkIndex | None = None
_elastic: ElasticChunkIndex | None = None


def require_elasticsearch_url() -> str:
    url = get_settings().elasticsearch_url.strip()
    if not url:
        raise EsNotConfiguredError("未配置 ELASTICSEARCH_URL，Hybrid 关键词路不可用")
    return url


def get_chunk_index() -> ChunkIndex:
    if _override is not None:
        return _override
    url = require_elasticsearch_url()
    global _elastic
    if _elastic is None:
        _elastic = ElasticChunkIndex(url)
    return _elastic


def upsert_chunks(
    chunks: list[tuple[uuid.UUID, str, uuid.UUID, uuid.UUID, str]],
) -> None:
    index = get_chunk_index()
    for chunk_id, content, knowledge_base_id, document_id, kind in chunks:
        index.upsert(
            chunk_id=chunk_id,
            content=content,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            kind=kind,
        )


def delete_document_chunks(document_id: uuid.UUID) -> None:
    get_chunk_index().delete_document(document_id)


def delete_knowledge_base_chunks(knowledge_base_id: uuid.UUID) -> None:
    get_chunk_index().delete_knowledge_base(knowledge_base_id)


def search_chunk_ids(
    query: str,
    *,
    knowledge_base_ids: Sequence[uuid.UUID],
    k: int,
    kind: str | None = None,
    document_id: uuid.UUID | None = None,
    document_ids: frozenset[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    return [cid for cid, _ in search_chunk_scores(
        query,
        knowledge_base_ids=knowledge_base_ids,
        k=k,
        kind=kind,
        document_id=document_id,
        document_ids=document_ids,
    )]


def search_chunk_scores(
    query: str,
    *,
    knowledge_base_ids: Sequence[uuid.UUID],
    k: int,
    kind: str | None = None,
    document_id: uuid.UUID | None = None,
    document_ids: frozenset[uuid.UUID] | None = None,
) -> list[tuple[uuid.UUID, float]]:
    return get_chunk_index().search(
        query,
        knowledge_base_ids=knowledge_base_ids,
        k=k,
        kind=kind,
        document_id=document_id,
        document_ids=document_ids,
    )
