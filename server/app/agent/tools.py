from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk, Entity, EntityLink, KnowledgeBase
from app.rag.search import SearchHit, search_chunks


def search_knowledge(
    session: Session,
    query: str,
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    kind: str | None = None,
    document_id: uuid.UUID | None = None,
    k: int = 5,
) -> list[SearchHit]:
    return search_chunks(
        session,
        query,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        tag_id=tag_id,
        kind=kind,
        document_id=document_id,
        k=k,
    )


def _web_hit(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or row.get("link") or "").strip()
    snippet = str(row.get("snippet") or row.get("content") or row.get("body") or "").strip()
    if not title and not url and not snippet:
        return None
    return {"title": title, "url": url, "snippet": snippet}


def _normalize_web_hits(payload: Any, *, k: int) -> list[dict[str, str]]:
    if k <= 0:
        return []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        raw = payload.get("results") or payload.get("items") or payload.get("data") or []
        rows = raw if isinstance(raw, list) else []
    else:
        rows = []
    out: list[dict[str, str]] = []
    for row in rows:
        hit = _web_hit(row)
        if hit is None:
            continue
        out.append(hit)
        if len(out) >= k:
            break
    return out


def web_search(query: str, *, k: int = 5) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    settings = get_settings()
    endpoint = settings.web_search_url.strip()
    if not endpoint:
        return []
    headers = {"User-Agent": "knowledge-realm/1.0"}
    key = settings.web_search_api_key.strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = httpx.post(
            endpoint,
            json={"query": q},
            headers=headers,
            timeout=float(settings.web_search_timeout),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return []
    return _normalize_web_hits(payload, k=k)

def _normalize(text: str) -> str:
    return " ".join(text.strip().split()).casefold()


def _matching_entity_ids(session: Session, knowledge_base_id: uuid.UUID, query: str) -> set[uuid.UUID]:
    q = _normalize(query)
    if not q:
        return set()
    rows = session.execute(
        select(Entity.id, Entity.name)
        .where(Entity.knowledge_base_id == knowledge_base_id)
    ).all()
    ids: set[uuid.UUID] = set()
    for eid, name in rows:
        n = _normalize(name)
        if q in n or n in q:
            ids.add(eid)
    return ids


def _expand_entity_ids(session: Session, seeds: set[uuid.UUID], hops: int = 2) -> dict[uuid.UUID, int]:
    distances: dict[uuid.UUID, int] = {eid: 0 for eid in seeds}
    if not seeds or hops <= 0:
        return distances
    current = set(seeds)
    for dist in range(1, hops + 1):
        if not current:
            break
        rows = session.execute(
            select(EntityLink.from_id, EntityLink.to_id)
            .where(
                (EntityLink.from_id.in_(current) | EntityLink.to_id.in_(current)),
            )
        ).all()
        nxt: set[uuid.UUID] = set()
        for from_id, to_id in rows:
            for eid in (from_id, to_id):
                if eid not in distances:
                    distances[eid] = dist
                    nxt.add(eid)
        current = nxt
    return distances


def _documents_for_entities(session: Session, entity_distances: dict[uuid.UUID, int]) -> dict[uuid.UUID, int]:
    """返回 document_id → 最小 hop 距离。"""
    if not entity_distances:
        return {}
    entity_ids = set(entity_distances.keys())
    doc_dist: dict[uuid.UUID, int] = {}
    rows = session.execute(
        select(EntityLink.document_id, EntityLink.from_id, EntityLink.to_id)
        .where(
            EntityLink.document_id.is_not(None),
            (EntityLink.from_id.in_(entity_ids) | EntityLink.to_id.in_(entity_ids)),
        )
    ).all()
    for doc_id, from_id, to_id in rows:
        if doc_id is None:
            continue
        # distance = min distance of connected entity
        d = min(entity_distances.get(from_id, 99), entity_distances.get(to_id, 99))
        if doc_id not in doc_dist or d < doc_dist[doc_id]:
            doc_dist[doc_id] = d
    return doc_dist


def search_graph(
    session: Session,
    query: str,
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    k: int = 5,
) -> list[SearchHit]:
    """基于知识图谱的检索：query 匹配实体名 → 沿关系扩展 1–2 跳 → 返回相关文档切片。"""
    kb = session.get(KnowledgeBase, knowledge_base_id)
    if kb is None or kb.user_id != user_id:
        return []
    seeds = _matching_entity_ids(session, knowledge_base_id, query)
    if not seeds:
        return []
    expanded = _expand_entity_ids(session, seeds, hops=2)
    doc_dist = _documents_for_entities(session, expanded)
    if not doc_dist:
        return []
    doc_ids = list(doc_dist.keys())
    # 取每个文档的前几个 chunk 作为代表（按 chunk_index）
    rows = session.execute(
        select(Document, DocumentChunk)
        .join(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(
            Document.id.in_(doc_ids),
            Document.status == "ready",
        )
        .order_by(Document.id, DocumentChunk.chunk_index)
    ).all()
    seen: set[uuid.UUID] = set()
    hits: list[SearchHit] = []
    for doc, chunk in rows:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        dist = doc_dist.get(doc.id, 99)
        score = max(0.1, 1.0 - dist * 0.3)
        hits.append(
            SearchHit(
                document_id=doc.id,
                document_name=doc.filename,
                chunk_id=chunk.id,
                content=chunk.content,
                score=score,
                page=chunk.page,
                heading=chunk.heading,
                kind=doc.kind,
            )
        )
        if len(hits) >= k:
            break
    return hits



def _links_for_entities(
    session: Session,
    entity_ids: set[uuid.UUID],
    *,
    rel: str | None = None,
) -> list[EntityLink]:
    if not entity_ids:
        return []
    stmt = select(EntityLink).where(
        EntityLink.from_id.in_(entity_ids),
        EntityLink.to_id.in_(entity_ids),
    )
    if rel:
        stmt = stmt.where(EntityLink.rel == rel)
    return list(session.scalars(stmt))


def _bfs_paths(
    seeds: set[uuid.UUID],
    links: list[EntityLink],
    max_hops: int,
) -> dict[uuid.UUID, list[EntityLink]]:
    """返回每个可达实体从某个 seed 出发的最短链路（以 EntityLink 列表表示）。"""
    if not seeds or max_hops <= 0:
        return {}
    adj: dict[uuid.UUID, list[EntityLink]] = {}
    for link in links:
        adj.setdefault(link.from_id, []).append(link)
        adj.setdefault(link.to_id, []).append(link)
    paths: dict[uuid.UUID, list[EntityLink]] = {}
    for seed in seeds:
        if seed not in adj:
            continue
        paths[seed] = []
        visited: set[uuid.UUID] = {seed}
        queue: list[tuple[uuid.UUID, list[EntityLink]]] = [(seed, [])]
        while queue:
            current, path = queue.pop(0)
            if len(path) >= max_hops:
                continue
            for link in adj.get(current, []):
                neighbor = link.to_id if link.from_id == current else link.from_id
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                new_path = path + [link]
                paths[neighbor] = new_path
                queue.append((neighbor, new_path))
    return paths


def search_graph_details(
    session: Session,
    query: str,
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    *,
    k: int = 5,
    max_hops: int = 2,
    rel: str | None = None,
) -> dict[str, Any]:
    """基于知识图谱的检索，返回实体、关系、路径与相关文档，供知识图谱页面「检索辅助」使用。"""
    kb = session.get(KnowledgeBase, knowledge_base_id)
    if kb is None or kb.user_id != user_id:
        return {"query": query, "entities": [], "links": [], "documents": [], "paths": []}

    seeds = _matching_entity_ids(session, knowledge_base_id, query)
    if not seeds:
        return {"query": query, "entities": [], "links": [], "documents": [], "paths": []}

    expanded = _expand_entity_ids(session, seeds, hops=max_hops)
    entity_ids = set(expanded.keys())
    links = _links_for_entities(session, entity_ids, rel=rel)

    # 文档命中：复用 search_graph 的文档收集逻辑
    doc_dist = _documents_for_entities(session, expanded)
    doc_ids = sorted(doc_dist.keys(), key=lambda d: doc_dist[d])[: max(k, 20)]

    documents: list[dict[str, Any]] = []
    if doc_ids:
        rows = session.execute(
            select(Document, DocumentChunk)
            .join(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(
                Document.id.in_(doc_ids),
                Document.status == "ready",
            )
            .order_by(Document.id, DocumentChunk.chunk_index)
        ).all()
        seen: set[uuid.UUID] = set()
        for doc, chunk in rows:
            if doc.id in seen:
                continue
            seen.add(doc.id)
            dist = doc_dist.get(doc.id, 99)
            documents.append(
                {
                    "document_id": doc.id,
                    "document_name": doc.filename,
                    "chunk_id": chunk.id,
                    "content": chunk.content,
                    "score": max(0.1, 1.0 - dist * 0.3),
                    "page": chunk.page,
                    "heading": chunk.heading,
                    "kind": doc.kind,
                }
            )
            if len(documents) >= k:
                break

    # 路径：从 seed 到文档关联实体的最短链路
    paths: list[list[EntityLink]] = []
    if links and documents:
        paths_map = _bfs_paths(seeds, links, max_hops)
        doc_entity_ids = set()
        for link in links:
            if link.document_id and link.document_id in doc_dist:
                doc_entity_ids.add(link.from_id)
                doc_entity_ids.add(link.to_id)
        for target in doc_entity_ids:
            path = paths_map.get(target)
            if path:
                paths.append(path)
        if len(paths) > 30:
            paths = paths[:30]

    entity_rows = list(session.scalars(select(Entity).where(Entity.id.in_(entity_ids))))
    return {
        "query": query,
        "entities": entity_rows,
        "links": links,
        "documents": documents,
        "paths": paths,
    }
