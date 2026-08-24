from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.storage import parsed_dir

TEXT_LIMIT = 12000


def gather_document_text(session: Session, doc: Document) -> str:
    chunks = list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
        )
    )
    if chunks:
        text = "\n\n".join(row.content for row in chunks if row.content)
        return text[:TEXT_LIMIT].strip()
    path = parsed_dir(doc.id) / "document.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")[:TEXT_LIMIT].strip()
    return ""


def _chat_complete(system: str, human: str) -> str:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{text}")])
    result = (prompt | model).invoke({"text": human})
    return str(result.content).strip()


def summarize_document(text: str) -> str:
    return _chat_complete(
        "根据用户给出的资料写一段中文摘要，不要编造资料中没有的事实。只输出摘要正文。",
        text,
    )


def suggest_tag_names(text: str) -> list[str]:
    raw = _chat_complete(
        "根据资料给出最多5个短标签。只输出 JSON 字符串数组，例如 [\"标签甲\",\"标签乙\"]。不要其它文字。",
        text,
    )
    names: list[str] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            names = [str(item).strip() for item in parsed]
    except json.JSONDecodeError:
        names = [part.strip() for part in raw.replace("，", ",").replace("\n", ",").split(",")]
    cleaned: list[str] = []
    seen: set[str] = set()
    for name in names:
        name = name.strip().strip("\"'")
        if not name or len(name) > 100 or name in seen:
            continue
        seen.add(name)
        cleaned.append(name)
        if len(cleaned) == 5:
            break
    return cleaned


def compare_documents(text_a: str, name_a: str, text_b: str, name_b: str) -> str:
    body = f"【文档A：{name_a}】\n{text_a}\n\n【文档B：{name_b}】\n{text_b}"
    return _chat_complete(
        "对比两篇资料。用中文写出相同点、不同点与简要结论。不要编造资料中没有的事实。只输出对比正文。",
        body,
    )
