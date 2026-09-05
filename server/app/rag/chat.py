from __future__ import annotations

import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.recorder import DecisionRecorder
from app.ingest.index import STATUS_READY
from app.kb import owned_document, resolve_knowledge_base_id
from app import llm as llm_mod
from app.models import Conversation, Message
from app.rag.search import SearchHit, search_chunks

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
    user_id: uuid.UUID,
    knowledge_base_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    k: int = 5,
    recorder: DecisionRecorder | None = None,
) -> tuple[Conversation, str, list[dict]]:
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id, user_id)
    if document_id is not None:
        doc = owned_document(session, document_id, user_id)
        if doc is None:
            raise LookupError("文档不存在")
        if doc.status != STATUS_READY:
            raise ValueError("文档未完成")
        if knowledge_base_id is not None and doc.knowledge_base_id != kb_id:
            raise ValueError("文档不属于该知识库")
    retrieve_started = time.monotonic()
    hits = search_chunks(
        session,
        query,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        k=k,
    )
    if recorder is not None:
        recorder.add_span(
            "retrieve",
            decision={"tool": "search_knowledge", "query": query, "k": k},
            evidence_refs=[
                {
                    "type": "chunk",
                    "id": str(hit.chunk_id),
                    "document_id": str(hit.document_id),
                    "document_name": hit.document_name,
                    "score": hit.score,
                    "excerpt": hit.content[:80],
                }
                for hit in hits
            ],
            metrics={"elapsed_ms": int((time.monotonic() - retrieve_started) * 1000), "hits": len(hits)},
        )
    if conversation_id is None:
        convo = Conversation(user_id=user_id, knowledge_base_id=kb_id, title=query[:40], mode="chat")
        session.add(convo)
        session.flush()
        history: list[tuple[str, str]] = []
    else:
        convo = session.get(Conversation, conversation_id)
        if convo is None or convo.user_id != user_id:
            raise LookupError("会话不存在")
        convo.mode = "chat"
        history = _history(session, convo.id)
    if recorder is not None:
        recorder.start_run(user_id=user_id, conversation_id=convo.id, mode="chat", query=query)
    if not llm_mod.llm_keys_ready():
        raise PermissionError("未配置 LLM API Key")
    generate_started = time.monotonic()
    if hits:
        context = "\n\n".join(f"[{hit.document_name}]\n{hit.content}" for hit in hits)
        answer = llm_mod.chat(query, context, history)
        cites = _citations(hits)
    else:
        answer = llm_mod.chat(query, "", history)
        cites = []
    if recorder is not None:
        recorder.add_span(
            "generate",
            decision={"summary": answer[:120]},
            metrics={"elapsed_ms": int((time.monotonic() - generate_started) * 1000)},
        )
    session.add(Message(conversation_id=convo.id, role="user", content=query, citations=None))
    assistant = Message(
        conversation_id=convo.id, role="assistant", content=answer, citations=cites or None
    )
    session.add(assistant)
    session.commit()
    session.refresh(convo)
    if recorder is not None:
        recorder.finish_run("success", message_id=assistant.id)
    return convo, answer, cites
