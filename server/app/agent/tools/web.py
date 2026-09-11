from __future__ import annotations

from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.tools._context import tool_runtime
from app.agent.tools.formatters import format_web_hits
from app.config import get_settings


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


@tool("web_search")
def web_search_tool(query: str, config: RunnableConfig) -> str:
    """互联网搜索。仅在允许联网（allow_web=true）且知识库证据不足，或问题需要外部最新信息时使用。

    禁止在知识库已足够时调用；禁止与相同 query 重复空转。库内事实仍优先 search_knowledge / search_graph。

    Args:
        query: 联网搜索查询
    """
    import json

    _, _, _, k = tool_runtime(config)
    hits = web_search(query, k=k)
    return json.dumps(
        {"text": format_web_hits(hits), "web_hits": hits, "citations": []},
        ensure_ascii=False,
    )
