from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.search import SearchHit, search_chunks


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


def _web_hit(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or row.get("link") or "").strip()
    snippet = str(row.get("snippet") or row.get("content") or row.get("body") or "").strip()
    if not title and not url and not snippet:
        return None
    return {"title": title, "url": url, "snippet": snippet}


def _normalize_web_hits(payload: Any, *, k: int) -> list[dict[str, str]]:
    if k <= 0:
        return []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        raw = payload.get("results") or payload.get("items") or payload.get("data") or []
        rows = raw if isinstance(raw, list) else []
    else:
        rows = []
    out: list[dict[str, str]] = []
    for row in rows:
        hit = _web_hit(row)
        if hit is None:
            continue
        out.append(hit)
        if len(out) >= k:
            break
    return out


def web_search(query: str, *, k: int = 5) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    settings = get_settings()
    endpoint = settings.web_search_url.strip()
    if not endpoint:
        return []
    headers = {"User-Agent": "knowledge-realm/1.0"}
    key = settings.web_search_api_key.strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = httpx.post(
            endpoint,
            json={"query": q},
            headers=headers,
            timeout=float(settings.web_search_timeout),
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return []
    return _normalize_web_hits(payload, k=k)
