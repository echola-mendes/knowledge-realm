from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.index import STATUS_READY
from app.models import Conversation, Document, Favorite, KnowledgeBase, Message
from app.search import search_chunks

MAX_RECENT_MESSAGES = 30
SEED_DAYS = 30
EXPAND_K = 5
OUTPUT_LIMIT = 5


def _recent_citation_document_ids(session: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """最近提问（Agent/Chat）中命中 citations 的文档 ID。"""
    since = datetime.now(timezone.utc) - timedelta(days=SEED_DAYS)
    rows = session.execute(
        select(Message.citations, Conversation.knowledge_base_id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Message.role == "assistant",
            Message.citations.is_not(None),
            Message.created_at >= since,
        )
        .order_by(Message.created_at.desc())
        .limit(MAX_RECENT_MESSAGES)
    ).all()
    ids: set[uuid.UUID] = set()
    for citations, _kb_id in rows:
        for item in citations or []:
            raw = item.get("document_id") if isinstance(item, dict) else None
            if raw:
                try:
                    ids.add(uuid.UUID(str(raw)))
                except ValueError:
                    continue
    return ids


def _favorite_document_ids(session: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = session.scalars(select(Favorite.document_id).where(Favorite.user_id == user_id)).all()
    return set(rows)


def _owned_ready_documents(
    session: Session, user_id: uuid.UUID, doc_ids: set[uuid.UUID]
) -> list[Document]:
    if not doc_ids:
        return []
    return list(
        session.scalars(
            select(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(
                Document.id.in_(doc_ids),
                Document.status == STATUS_READY,
                KnowledgeBase.user_id == user_id,
            )
        ).all()
    )


def recommend_documents(session: Session, user_id: uuid.UUID) -> list[dict]:
    """聚合收藏 + 最近 citation 文档作为种子，搜索相似文档，去重排除已收藏/种子本体，取前 5。"""
    favorites = _favorite_document_ids(session, user_id)
    citation_ids = _recent_citation_document_ids(session, user_id)
    seed_ids = favorites | citation_ids
    seed_docs = _owned_ready_documents(session, user_id, seed_ids)

    scores: defaultdict[uuid.UUID, float] = defaultdict(float)
    for seed in seed_docs:
        query = (seed.summary or "").strip() or seed.filename
        try:
            hits = search_chunks(
                session,
                query,
                user_id=user_id,
                knowledge_base_id=seed.knowledge_base_id,
                k=EXPAND_K,
            )
        except Exception:  # noqa: BLE001
            continue
        for hit in hits:
            if hit.document_id in seed_ids:
                continue
            scores[hit.document_id] += hit.score

    if not scores:
        return []

    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:OUTPUT_LIMIT]
    doc_ids = {doc_id for doc_id, _ in ordered}
    docs = {d.id: d for d in _owned_ready_documents(session, user_id, doc_ids)}
    out: list[dict] = []
    for doc_id, score in ordered:
        doc = docs.get(doc_id)
        if doc is None:
            continue
        out.append(
            {
                "document_id": doc_id,
                "document_name": doc.filename,
                "knowledge_base_id": doc.knowledge_base_id,
                "score": score,
                "kind": doc.kind,
            }
        )
    return out
