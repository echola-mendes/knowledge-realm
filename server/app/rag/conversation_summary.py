from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rag.chat import HISTORY_LIMIT
from app.models import Conversation, Message
from app.chains import summarize_conversation_turns


def refresh_conversation_summary(session: Session, conversation_id: uuid.UUID) -> None:
    rows = list(
        session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        ).all()
    )
    if len(rows) <= HISTORY_LIMIT:
        return
    convo = session.get(Conversation, conversation_id)
    if convo is None:
        return
    older = rows[:-HISTORY_LIMIT]
    dialogue = "\n".join(
        f"{'用户' if row.role == 'user' else '助手'}：{row.content}" for row in older if row.content
    )
    if not dialogue.strip():
        return
    convo.summary = summarize_conversation_turns(dialogue)
