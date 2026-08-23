from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.chat import run_chat
from app.routers.documents import get_db
from app.schemas import ChatRequest, ChatResponse, CitationOut

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat_api(body: ChatRequest, session: Session = Depends(get_db)):
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
