from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import index as index_mod
from app.chat import run_chat
from app.models import Conversation, Message
from app.routers.documents import get_db
from app.schemas import ChatRequest, ChatResponse, CitationOut, ConversationOut, MessageOut

router = APIRouter(prefix="/api", tags=["chat"])


def _http_chat(body: ChatRequest, session: Session) -> ChatResponse:
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    try:
        convo, answer, cites = run_chat(
            session,
            body.query,
            knowledge_base_id=body.knowledge_base_id,
            document_id=body.document_id,
            conversation_id=body.conversation_id,
            k=body.k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(
        conversation_id=convo.id,
        answer=answer,
        citations=[CitationOut.model_validate(item) for item in cites],
    )


@router.post("/chat", response_model=ChatResponse)
def chat_api(body: ChatRequest, session: Session = Depends(get_db)):
    return _http_chat(body, session)


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request, session: Session = Depends(get_db)):
    result = _http_chat(body, session)

    async def events():
        for char in result.answer:
            if await request.is_disconnected():
                return
            yield f"data: {json.dumps({'type': 'token', 'text': char}, ensure_ascii=False)}\n\n"
        payload = {
            "type": "citations",
            "conversation_id": str(result.conversation_id),
            "answer": result.answer,
            "citations": [item.model_dump(mode="json") for item in result.citations],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    knowledge_base_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
):
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())
    if knowledge_base_id is not None:
        stmt = stmt.where(Conversation.knowledge_base_id == knowledge_base_id)
    return session.scalars(stmt).all()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: uuid.UUID, session: Session = Depends(get_db)):
    convo = session.get(Conversation, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    ).all()


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: uuid.UUID, session: Session = Depends(get_db)):
    convo = session.get(Conversation, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.execute(delete(Message).where(Message.conversation_id == conversation_id))
    session.delete(convo)
    session.commit()
    return {"ok": True}
