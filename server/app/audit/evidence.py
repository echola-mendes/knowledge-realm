from __future__ import annotations

from typing import Any

from app.rag.search import SearchHit

_EXCERPT_LEN = 120


def _excerpt(text: str, max_len: int = _EXCERPT_LEN) -> str:
    return text[:max_len]


def _assembly_kind(hit: SearchHit) -> str:
    original = hit.original_content or hit.content
    if hit.expanded_chunk_ids or hit.content != original:
        return "neighbor_expand"
    return "child_only"


def search_hit_evidence_ref(
    hit: SearchHit,
    *,
    qi_id: str | None = None,
) -> dict[str, Any]:
    """Map a post-assembly SearchHit to a decision-audit evidence ref."""
    original = hit.original_content or hit.content
    assembly = _assembly_kind(hit)
    neighbor_ids = [str(cid) for cid in hit.neighbor_chunk_ids]
    expanded_ids = [str(cid) for cid in hit.expanded_chunk_ids]
    seed_ids = [str(cid) for cid in hit.seed_chunk_ids] or [str(hit.chunk_id)]
    expanded_set = set(hit.expanded_chunk_ids)
    dropped = [str(cid) for cid in hit.neighbor_chunk_ids if cid not in expanded_set]
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
        "seed_chunk_ids": seed_ids,
        "neighbor_chunk_ids": neighbor_ids,
        "expanded_chunk_ids": expanded_ids,
        "dropped": dropped,
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
    counts = {"child_only": 0, "neighbor_expand": 0}
    for hit in hits:
        counts[_assembly_kind(hit)] += 1
    return counts
