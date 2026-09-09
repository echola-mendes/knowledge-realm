from __future__ import annotations

from typing import Any

from app.rag.search import SearchHit

_EXCERPT_LEN = 120


def _excerpt(text: str, max_len: int = _EXCERPT_LEN) -> str:
    return text[:max_len]


def _assembly_kind(hit: SearchHit) -> str:
    original = hit.original_content or hit.content
    if original == hit.content:
        return "child_only"
    if hit.parent_id is not None:
        return "parent"
    if hit.heading:
        return "heading_expand"
    return "expanded"


def search_hit_evidence_ref(
    hit: SearchHit,
    *,
    qi_id: str | None = None,
) -> dict[str, Any]:
    """Map a post-assembly SearchHit to a decision-audit evidence ref."""
    original = hit.original_content or hit.content
    assembly = _assembly_kind(hit)
    ref: dict[str, Any] = {
        "type": "chunk",
        "id": str(hit.chunk_id),
        "chunk_id": str(hit.chunk_id),
        "document_id": str(hit.document_id),
        "document_name": hit.document_name,
        "score": hit.score,
        "assembly": assembly,
        "excerpt": _excerpt(hit.content),
        "context_chars": len(hit.content),
    }
    if original != hit.content:
        ref["original_excerpt"] = _excerpt(original)
        ref["original_chars"] = len(original)
    if hit.parent_id is not None:
        ref["parent_id"] = str(hit.parent_id)
    if hit.heading:
        ref["heading"] = hit.heading
    if qi_id is not None:
        ref["qi_id"] = qi_id
    return ref


def context_assembly_summary(hits: list[SearchHit]) -> dict[str, int]:
    counts = {"child_only": 0, "parent": 0, "heading_expand": 0, "expanded": 0}
    for hit in hits:
        counts[_assembly_kind(hit)] += 1
    return counts
