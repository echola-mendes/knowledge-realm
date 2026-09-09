"""Evidence Pool Merge — dedup, budget, related_questions, merge-span payload."""

from __future__ import annotations

from typing import Any

from app.agent.sufficiency import knowledge_span_decision
from app.rag.search import SearchHit

MAX_EVIDENCE = 10


def evidence_from_hit(
    hit: SearchHit,
    *,
    qi_id: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Normalize a SearchHit into an Evidence Pool item."""
    related: list[str] = []
    if question:
        related.append(question)
    item: dict[str, Any] = {
        "id": str(hit.chunk_id),
        "document_id": str(hit.document_id),
        "document_name": hit.document_name,
        "chunk_id": str(hit.chunk_id),
        "parent_id": str(hit.parent_id) if hit.parent_id is not None else None,
        "score": float(hit.score),
        "content": hit.content,
        "related_questions": related,
    }
    if qi_id is not None:
        item["qi_id"] = qi_id
    return item


def _dedup_key(item: dict[str, Any]) -> str:
    parent_id = item.get("parent_id")
    if parent_id:
        return f"parent:{parent_id}"
    chunk_id = item.get("chunk_id") or item.get("id")
    return f"chunk:{chunk_id}"


def _merge_related(a: list[str], b: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for q in list(a or []) + list(b or []):
        text = str(q).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _by_qi(pool: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouping: dict[str, list[str]] = {}
    for item in pool:
        qi = item.get("qi_id")
        if qi is None:
            continue
        key = str(qi)
        eid = str(item.get("id") or item.get("chunk_id") or "")
        if not eid:
            continue
        grouping.setdefault(key, [])
        if eid not in grouping[key]:
            grouping[key].append(eid)
    return grouping


def merge_evidence(
    pool: list[dict[str, Any]] | None,
    *,
    max_evidence: int = MAX_EVIDENCE,
) -> dict[str, Any]:
    """
    Dedup by parent_id (else chunk_id), keep highest score, merge related_questions,
    then keep Top-N by score.

    Returns dict with merged, dropped, input_count, by_qi (pre-merge).
    """
    items = list(pool or [])
    by_qi = _by_qi(items)
    input_count = len(items)
    input_ids = [str(i.get("id") or i.get("chunk_id") or "") for i in items]

    best: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _dedup_key(item)
        cur = best.get(key)
        if cur is None:
            best[key] = {
                **item,
                "related_questions": list(item.get("related_questions") or []),
            }
            continue
        merged_related = _merge_related(
            list(cur.get("related_questions") or []),
            list(item.get("related_questions") or []),
        )
        if float(item.get("score") or 0) > float(cur.get("score") or 0):
            kept = {**item, "related_questions": merged_related}
        else:
            kept = {**cur, "related_questions": merged_related}
        best[key] = kept

    ranked = sorted(
        best.values(),
        key=lambda x: float(x.get("score") or 0),
        reverse=True,
    )
    merged = ranked[: max(0, int(max_evidence))]
    kept_ids = {str(i.get("id") or i.get("chunk_id") or "") for i in merged}
    dropped = [eid for eid in input_ids if eid and eid not in kept_ids]
    # unique dropped preserving order
    seen_drop: set[str] = set()
    dropped_unique: list[str] = []
    for eid in dropped:
        if eid in seen_drop:
            continue
        seen_drop.add(eid)
        dropped_unique.append(eid)

    return {
        "merged": merged,
        "dropped": dropped_unique,
        "input_count": input_count,
        "by_qi": by_qi,
    }


def merge_decision(result: dict[str, Any]) -> dict[str, Any]:
    """route-span decision for merge: input/output with before/after counts."""
    merged = list(result.get("merged") or [])
    dropped = list(result.get("dropped") or [])
    return knowledge_span_decision(
        "merge",
        input={
            "count": int(result.get("input_count") or 0),
            "by_qi": dict(result.get("by_qi") or {}),
        },
        output={
            "count": len(merged),
            "ids": [str(i.get("id") or i.get("chunk_id") or "") for i in merged],
            "dropped": dropped,
            "related_questions": {
                str(i.get("id") or i.get("chunk_id") or ""): list(
                    i.get("related_questions") or []
                )
                for i in merged
                if i.get("related_questions")
            },
        },
    )


def merge_evidence_refs(merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact evidence_refs for merge span (id + excerpt, no full parent dump)."""
    refs: list[dict[str, Any]] = []
    for item in merged:
        content = str(item.get("content") or "")
        ref: dict[str, Any] = {
            "type": "chunk",
            "id": str(item.get("id") or item.get("chunk_id") or ""),
            "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
            "document_id": str(item.get("document_id") or ""),
            "document_name": item.get("document_name"),
            "score": item.get("score"),
            "excerpt": content[:120],
        }
        if item.get("parent_id"):
            ref["parent_id"] = str(item["parent_id"])
        if item.get("related_questions"):
            ref["related_questions"] = list(item["related_questions"])
        refs.append(ref)
    return refs
