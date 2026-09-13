"""Evidence Sufficiency rules — knowledge_flow V0 + ReAct precheck (not sufficiency)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

SufficiencyStatus = Literal["SUFFICIENT", "INSUFFICIENT"]

SUFFICIENT: SufficiencyStatus = "SUFFICIENT"
INSUFFICIENT: SufficiencyStatus = "INSUFFICIENT"
RULE_V0 = "len(hits)>0"

PrecheckStatus = Literal["NO_VALID_EVIDENCE", "HAS_VALID_EVIDENCE"]
NO_VALID_EVIDENCE: PrecheckStatus = "NO_VALID_EVIDENCE"
HAS_VALID_EVIDENCE: PrecheckStatus = "HAS_VALID_EVIDENCE"

_REQUIRED_FIELDS = ("id", "content")


# V0: any hit counts as sufficient; score ignored. Used by knowledge_flow.
def sufficiency_v0(hits: Sequence[Any]) -> SufficiencyStatus:
    """Return SUFFICIENT iff hits is non-empty."""
    return SUFFICIENT if len(hits) > 0 else INSUFFICIENT


def _evidence_id(item: Mapping[str, Any]) -> str:
    raw = item.get("id") or item.get("chunk_id")
    return str(raw).strip() if raw is not None else ""


def _is_valid_evidence_item(item: Mapping[str, Any]) -> bool:
    if not isinstance(item, Mapping):
        return False
    if not _evidence_id(item):
        return False
    content = item.get("content")
    if content is None:
        return False
    if not str(content).strip():
        return False
    return True


# ReAct gate only: whether evidence is eligible for LLM sufficiency (NOT "enough to answer").
def precheck_evidence(
    evidence: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Dedup + field checks → NO_VALID_EVIDENCE | HAS_VALID_EVIDENCE.

    len(hits)>0 alone is never treated as sufficient for answering.
    """
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    for raw in evidence or []:
        if not isinstance(raw, Mapping):
            continue
        if not _is_valid_evidence_item(raw):
            continue
        eid = _evidence_id(raw)
        if eid in seen:
            continue
        seen.add(eid)
        valid.append(dict(raw))

    status: PrecheckStatus = HAS_VALID_EVIDENCE if valid else NO_VALID_EVIDENCE
    return {
        "status": status,
        "valid_evidence": valid,
        "valid_count": len(valid),
    }


def knowledge_span_decision(
    step: str,
    *,
    input: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    """Canonical knowledge-agent span payload: decision.{step,input,output}."""
    return {"step": step, "input": input, "output": output}


# Audit/span wrapper around sufficiency_v0 (knowledge_flow).
def sufficiency_decision(
    hits: Sequence[Any],
    *,
    qi_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Build a route-span decision for the V0 sufficiency step."""
    status = sufficiency_v0(hits)
    hit_count = len(hits)
    inp: dict[str, Any] = {"hit_count": hit_count}
    if qi_id is not None:
        inp["qi_id"] = qi_id
    if query is not None:
        inp["query"] = query
    return knowledge_span_decision(
        "sufficiency",
        input=inp,
        output={"status": status, "rule": RULE_V0, "hit_count": hit_count},
    )
