from __future__ import annotations

from app.agent.text2sql import rows_preview
from app.rag.search import SearchHit


def format_search_hits(hits: list[SearchHit]) -> str:
    if not hits:
        return "未找到相关文档。"
    return "\n\n".join(f"[{h.document_name}]\n{h.content}" for h in hits)


def format_web_hits(hits: list[dict[str, str]]) -> str:
    if not hits:
        return "未找到相关网页。"
    return "\n\n".join(
        f"[{h.get('title') or h.get('url')}]\n{h.get('url') or ''}\n{h.get('snippet') or ''}".strip()
        for h in hits
    )


def format_sql_result(result: dict) -> str:
    parts = [f"SQL: {result.get('sql') or ''}"]
    if result.get("error"):
        parts.append(f"错误: {result['error']}")
    parts.append(rows_preview(list(result.get("rows") or [])))
    return "\n".join(parts)
