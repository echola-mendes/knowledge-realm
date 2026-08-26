from __future__ import annotations

import json
import re

from app.config import get_settings

RERANK_CANDIDATE_MAX = 20


def rerank_keys_ready() -> bool:
    return bool(get_settings().rerank_api_key.strip())


def score_documents(query: str, documents: list[str]) -> list[float] | None:
    """Return per-document scores, or None to keep original order."""
    if not documents:
        return []
    if rerank_keys_ready():
        try:
            return _compatible_rerank_scores(query, documents)
        except Exception:  # noqa: BLE001
            pass
    if get_settings().llm_api_key.strip():
        try:
            return _llm_rerank_scores(query, documents)
        except Exception:  # noqa: BLE001
            return None
    return None


def _rerank_url() -> str:
    base = get_settings().rerank_base_url.rstrip("/")
    if base.endswith("/rerank") or base.endswith("/reranks"):
        return base
    return f"{base}/reranks"


def _compatible_rerank_scores(query: str, documents: list[str]) -> list[float]:
    import httpx

    s = get_settings()
    payload = {
        "model": s.rerank_model,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }
    resp = httpx.post(
        _rerank_url(),
        headers={"Authorization": f"Bearer {s.rerank_api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or (data.get("output") or {}).get("results") or []
    scores = [0.0] * len(documents)
    for item in results:
        idx = int(item.get("index", 0))
        if 0 <= idx < len(scores):
            scores[idx] = float(item.get("relevance_score", item.get("score", 0.0)))
    return scores


def _llm_rerank_scores(query: str, documents: list[str]) -> list[float]:
    from langchain_openai import ChatOpenAI

    s = get_settings()
    numbered = "\n".join(f"{i}. {text[:800]}" for i, text in enumerate(documents))
    prompt = (
        "对每个候选相对问题打相关性分（0到1）。只输出 JSON 数组，长度等于候选数，不要其它文字。\n"
        f"问题：{query}\n候选：\n{numbered}"
    )
    model = ChatOpenAI(
        model=s.llm_model,
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        temperature=0,
    )
    raw = str(model.invoke(prompt).content)
    match = re.search(r"\[[\s\S]*\]", raw)
    if match is None:
        raise ValueError("llm_rerank_not_json")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list) or len(parsed) != len(documents):
        raise ValueError("llm_rerank_length")
    return [float(x) for x in parsed]
