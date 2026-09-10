from __future__ import annotations

import json
import uuid

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.agent.tools._context import tool_runtime
from app.agent.tools.formatters import format_search_hits
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


def _hit_citation(hit: SearchHit) -> dict:
    return {
        "document_id": str(hit.document_id),
        "document_name": hit.document_name,
        "chunk_id": str(hit.chunk_id),
        "page_start": hit.page,
        "page_end": hit.page,
        "content": hit.content,
        "score": hit.score,
    }


@tool("search_knowledge")
def search_knowledge_tool(query: str, config: RunnableConfig) -> str:
    """在用户知识库中检索相关文档片段。

    Args:
        query: 检索关键词
    """
    session, user_id, knowledge_base_id, k = tool_runtime(config)
    if session is None or user_id is None:
        return json.dumps({"text": "检索失败：缺少运行时上下文。", "citations": []}, ensure_ascii=False)
    hits = search_knowledge(
        session,
        query,
        user_id,
        knowledge_base_id=knowledge_base_id,
        k=k,
    )
    return json.dumps(
        {
            "text": format_search_hits(hits),
            "citations": [_hit_citation(h) for h in hits],
        },
        ensure_ascii=False,
    )
