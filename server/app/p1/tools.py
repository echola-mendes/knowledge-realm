from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.search import SearchHit, search_chunks


def search_knowledge(
    session: Session,
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    kind: str | None = None,
    document_id: uuid.UUID | None = None,
    k: int = 5,
) -> list[SearchHit]:
    return search_chunks(
        session,
        query,
        knowledge_base_id=knowledge_base_id,
        tag_id=tag_id,
        kind=kind,
        document_id=document_id,
        k=k,
    )
