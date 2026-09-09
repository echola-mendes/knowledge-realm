"""Evidence Sufficiency V0 — pure rule, no LLM."""

from __future__ import annotations

from typing import Any, Literal, Sequence

SufficiencyStatus = Literal["SUFFICIENT", "INSUFFICIENT"]

SUFFICIENT: SufficiencyStatus = "SUFFICIENT"
INSUFFICIENT: SufficiencyStatus = "INSUFFICIENT"
RULE_V0 = "len(hits)>0"


def sufficiency_v0(hits: Sequence[Any]) -> SufficiencyStatus:
    """V0: any SearchHit counts as sufficient; score is ignored."""
    return SUFFICIENT if len(hits) > 0 else INSUFFICIENT


def knowledge_span_decision(
    step: str,
    *,
    input: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    """Canonical knowledge-agent span payload: decision.{step,input,output}."""
    return {"step": step, "input": input, "output": output}


def sufficiency_decision(
    hits: Sequence[Any],
    *,
    qi_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Build a route-span decision for the sufficiency step."""
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
