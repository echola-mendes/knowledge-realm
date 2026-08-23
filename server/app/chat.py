from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.index import STATUS_READY
from app.kb import resolve_knowledge_base_id
from app import llm as llm_mod
from app.models import Conversation, Document, Message
from app.search import SearchHit, search_chunks

HISTORY_LIMIT = 6


def _citations(hits: list[SearchHit]) -> list[dict]:
    return [
        {
            "document_id": str(hit.document_id),
            "document_name": hit.document_name,
            "chunk_id": str(hit.chunk_id),
            "page_start": hit.page,
            "page_end": hit.page,
            "content": hit.content,
            "score": hit.score,
        }
        for hit in hits
    ]


def _history(session: Session, conversation_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    ).all()
    return [(row.role, row.content) for row in rows[-HISTORY_LIMIT:]]


def run_chat(
    session: Session,
    query: str,
    *,
    knowledge_base_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    k: int = 5,
) -> tuple[Conversation, str, list[dict]]:
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id)
    if document_id is not None:
        doc = session.get(Document, document_id)
        if doc is None:
            raise LookupError("文档不存在")
        if doc.status != STATUS_READY:
            raise ValueError("文档未完成")
        if doc.knowledge_base_id != kb_id:
            raise ValueError("文档不属于该知识库")
    hits = search_chunks(
        session,
        query,
        knowledge_base_id=kb_id,
        document_id=document_id,
        k=k,
    )
    if conversation_id is None:
        convo = Conversation(knowledge_base_id=kb_id, title=query[:40])
        session.add(convo)
        session.flush()
        history: list[tuple[str, str]] = []
    else:
        convo = session.get(Conversation, conversation_id)
        if convo is None:
            raise LookupError("会话不存在")
        history = _history(session, convo.id)
    if not hits:
        answer = llm_mod.NO_HIT_TEXT
        cites: list[dict] = []
    else:
        if not llm_mod.llm_keys_ready():
            raise PermissionError("未配置 LLM API Key")
        context = "\n\n".join(f"[{hit.document_name}]\n{hit.content}" for hit in hits)
        answer = llm_mod.chat(query, context, history)
        cites = _citations(hits)
    session.add(Message(conversation_id=convo.id, role="user", content=query, citations=None))
    session.add(Message(conversation_id=convo.id, role="assistant", content=answer, citations=cites or None))
    session.commit()
    session.refresh(convo)
    return convo, answer, cites
