from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.deps import current_user
from app.kb import KnowledgeBaseAccessError, owned_document, resolve_knowledge_base_id
from app.llm import llm_keys_ready
from app.models import Conversation, Document, Entity, EntityLink, Message, User
from app.p1.chains import compare_documents, gather_document_text
from app.p1.graph import build_graph, initial_state
from app.chat import _history
from app.schemas import (
    AgentOut,
    AgentRequest,
    CitationOut,
    CompareOut,
    CompareRequest,
    GraphEntityOut,
    GraphLinkOut,
    KnowledgeGraphOut,
)

router = APIRouter(prefix="/api", tags=["p1"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _load_ready(session: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = owned_document(session, document_id, user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail="文档未完成")
    return doc


@router.post("/compare", response_model=CompareOut)
def compare(body: CompareRequest, session: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.document_id_a == body.document_id_b:
        raise HTTPException(status_code=400, detail="须选择两篇不同文档")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    doc_a = _load_ready(session, body.document_id_a, user.id)
    doc_b = _load_ready(session, body.document_id_b, user.id)
    if doc_a.knowledge_base_id != doc_b.knowledge_base_id:
        raise HTTPException(status_code=400, detail="两篇文档须属于同一知识库")
    text_a = gather_document_text(session, doc_a)
    text_b = gather_document_text(session, doc_b)
    if not text_a or not text_b:
        raise HTTPException(status_code=400, detail="empty_content")
    comparison = compare_documents(text_a, doc_a.filename, text_b, doc_b.filename)
    return CompareOut(
        document_id_a=doc_a.id,
        document_id_b=doc_b.id,
        comparison=comparison,
    )


def _agent_out(body: AgentRequest, session: Session, user_id: uuid.UUID) -> AgentOut:
    if body.task not in ("agent", "report"):
        raise HTTPException(status_code=400, detail="task 须为 agent 或 report")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    try:
        kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id, user_id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if body.conversation_id is None:
        convo = Conversation(user_id=user_id, knowledge_base_id=kb_id, title=body.query[:40])
        session.add(convo)
        session.flush()
        history_msgs: list[dict[str, str]] = []
        summary_text = ""
    else:
        convo = session.get(Conversation, body.conversation_id)
        if convo is None or convo.user_id != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        history_msgs = [{"role": role, "content": content} for role, content in _history(session, convo.id)]
        summary_text = ""
    task = "report" if body.task == "report" else "agent"
    out = build_graph().invoke(
        initial_state(
            body.query,
            knowledge_base_id=body.knowledge_base_id,
            task=task,
            history=history_msgs,
        ),
        config={
            "configurable": {
                "thread_id": str(convo.id),
                "session": session,
                "user_id": user_id,
            }
        },
    )
    answer = out.get("answer") or ""
    cites = [CitationOut.model_validate(item) for item in (out.get("citations") or [])]
    session.add(Message(conversation_id=convo.id, role="user", content=body.query, citations=None))
    session.add(
        Message(
            conversation_id=convo.id,
            role="assistant",
            content=answer,
            citations=[c.model_dump(mode="json") for c in cites] or None,
        )
    )
    session.commit()
    session.refresh(convo)
    return AgentOut(
        task=task,
        knowledge_base_id=kb_id,
        conversation_id=convo.id,
        answer=answer,
        citations=cites,
        loop_count=int(out.get("loop_count") or 0),
    )


@router.post("/agent", response_model=AgentOut)
def agent_run(body: AgentRequest, session: Session = Depends(get_db), user: User = Depends(current_user)):
    return _agent_out(body, session, user.id)


@router.post("/agent/stream")
async def agent_stream(
    body: AgentRequest, request: Request, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    result = _agent_out(body, session, user.id)

    async def events():
        for char in result.answer:
            if await request.is_disconnected():
                return
            yield f"data: {json.dumps({'type': 'token', 'text': char}, ensure_ascii=False)}\n\n"
        payload = {"type": "citations", **result.model_dump(mode="json")}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


def _graph_out(entities: list[Entity], links: list[EntityLink]) -> KnowledgeGraphOut:
    return KnowledgeGraphOut(
        entities=[GraphEntityOut(id=row.id, name=row.name, type=row.type) for row in entities],
        links=[
            GraphLinkOut(from_id=row.from_id, to_id=row.to_id, rel=row.rel, document_id=row.document_id)
            for row in links
        ],
    )


@router.get("/graph", response_model=KnowledgeGraphOut)
def get_graph(
    knowledge_base_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        kb_id = resolve_knowledge_base_id(session, knowledge_base_id, user.id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if document_id is not None:
        doc = owned_document(session, document_id, user.id)
        if doc is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if doc.knowledge_base_id != kb_id:
            return _graph_out([], [])
        link_rows = list(session.scalars(select(EntityLink).where(EntityLink.document_id == document_id)))
        ids = {row.from_id for row in link_rows} | {row.to_id for row in link_rows}
        entity_rows: list[Entity] = []
        if ids:
            entity_rows = list(
                session.scalars(select(Entity).where(Entity.id.in_(ids), Entity.knowledge_base_id == kb_id))
            )
        allowed = {row.id for row in entity_rows}
        link_rows = [row for row in link_rows if row.from_id in allowed and row.to_id in allowed]
        return _graph_out(entity_rows, link_rows)
    entity_rows = list(session.scalars(select(Entity).where(Entity.knowledge_base_id == kb_id)))
    ids = {row.id for row in entity_rows}
    link_rows: list[EntityLink] = []
    if ids:
        link_rows = list(session.scalars(select(EntityLink).where(EntityLink.from_id.in_(ids))))
    return _graph_out(entity_rows, link_rows)
