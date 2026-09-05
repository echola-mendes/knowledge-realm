from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingest import index as index_mod
from app.rag.chat import run_chat
from app.deps import current_user
from app.kb import KnowledgeBaseAccessError
from app.models import Conversation, Message, User
from app.routers.documents import get_db
from app.schemas import ChatRequest, ChatResponse, CitationOut, ConversationOut, ConversationPatch, MessageOut
from app.message_ui import hydrate_plan_html_from_records, message_to_out

router = APIRouter(prefix="/api", tags=["chat"])


def _http_chat(body: ChatRequest, session: Session, user_id: uuid.UUID) -> ChatResponse:
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    try:
        convo, answer, cites = run_chat(
            session,
            body.query,
            user_id=user_id,
            knowledge_base_id=body.knowledge_base_id,
            document_id=body.document_id,
            conversation_id=body.conversation_id,
            k=body.k,
        )
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
def chat_api(body: ChatRequest, session: Session = Depends(get_db), user: User = Depends(current_user)):
    return _http_chat(body, session, user.id)


@router.post("/chat/stream")
def chat_stream(
    body: ChatRequest, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    """必须用 def：_http_chat 为同步调用，async def 会占满事件循环，侧栏导航的 /me 会一起卡住。"""
    result = _http_chat(body, session, user.id)

    def events():
        for char in result.answer:
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
    user: User = Depends(current_user),
):
    stmt = select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    if knowledge_base_id is not None:
        stmt = stmt.where(Conversation.knowledge_base_id == knowledge_base_id)
    return session.scalars(stmt).all()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    convo = session.get(Conversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    ).all()
    out = [message_to_out(m) for m in rows]
    return hydrate_plan_html_from_records(session, conversation_id, out)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    convo = session.get(Conversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.execute(delete(Message).where(Message.conversation_id == conversation_id))
    session.delete(convo)
    session.commit()
    return {"ok": True}


_CONVERSATION_MODES = frozenset({"chat", "knowledge", "agent", "report"})


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def patch_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatch,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    convo = session.get(Conversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="标题不能为空")
        convo.title = title[:80]
    if body.mode is not None:
        if body.mode not in _CONVERSATION_MODES:
            raise HTTPException(status_code=422, detail="mode 无效")
        convo.mode = body.mode
    session.commit()
    session.refresh(convo)
    return convo
