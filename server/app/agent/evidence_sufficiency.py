"""ReAct LLM Evidence Sufficiency — structured judge (separate from knowledge_flow V0)."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from app.agent.sufficiency import (
    HAS_VALID_EVIDENCE,
    INSUFFICIENT,
    NO_VALID_EVIDENCE,
    precheck_evidence,
)


class EvidenceSufficiencyResult(BaseModel):
    """Structured LLM output for evidence sufficiency."""

    sufficient: bool = False
    covered_aspects: list[str] = Field(default_factory=list)
    missing_aspects: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    reason: str = ""


def _clip_evidence_for_prompt(
    evidence: Sequence[Mapping[str, Any]],
    *,
    limit: int = 12,
    content_chars: int = 400,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in list(evidence)[:limit]:
        out.append(
            {
                "id": item.get("id") or item.get("chunk_id"),
                "qi_id": item.get("qi_id"),
                "document_name": item.get("document_name"),
                "content": str(item.get("content") or "")[:content_chars],
            }
        )
    return out


def _insufficient_no_evidence(*, reason: str = "no valid evidence after precheck") -> dict[str, Any]:
    result = EvidenceSufficiencyResult(
        sufficient=False,
        covered_aspects=[],
        missing_aspects=[],
        gaps=["无有效检索证据"],
        reason=reason,
    )
    return {
        "precheck": NO_VALID_EVIDENCE,
        "llm_called": False,
        **result.model_dump(),
        "status": INSUFFICIENT,
    }


def _parse_llm_payload(raw: Any) -> EvidenceSufficiencyResult:
    if isinstance(raw, EvidenceSufficiencyResult):
        return raw
    if isinstance(raw, BaseModel):
        return EvidenceSufficiencyResult.model_validate(raw.model_dump())
    if isinstance(raw, dict):
        return EvidenceSufficiencyResult.model_validate(raw)
    text = str(raw or "")
    start = text.find("{")
    end = text.rfind("}")
    payload = text[start : end + 1] if start >= 0 and end >= start else text
    return EvidenceSufficiencyResult.model_validate(json.loads(payload))


def evaluate_evidence_sufficiency(
    *,
    user_question: str,
    evidence: Sequence[Mapping[str, Any]] | None,
    sub_questions: Sequence[Mapping[str, Any]] | None = None,
    qi: Mapping[str, Any] | None = None,
    aspects: Sequence[str] | None = None,
    llm_invoke=None,
) -> dict[str, Any]:
    """Rule precheck then optional LLM structured sufficiency.

    llm_invoke: optional callable(messages)->result for tests; default uses ChatOpenAI.
    """
    gate = precheck_evidence(evidence)
    if gate["status"] == NO_VALID_EVIDENCE:
        return _insufficient_no_evidence()

    valid = list(gate["valid_evidence"])
    qi_obj = dict(qi) if qi else None
    aspect_list = [str(a).strip() for a in (aspects or []) if str(a).strip()]
    if not aspect_list and qi_obj:
        aspect_list = [str(a).strip() for a in (qi_obj.get("aspects") or []) if str(a).strip()]
    if not aspect_list and qi_obj and qi_obj.get("question"):
        aspect_list = [str(qi_obj["question"])]

    qi_block = ""
    if qi_obj:
        qi_block = (
            f"当前子问题 id={qi_obj.get('id')}\n"
            f"question={qi_obj.get('question')}\n"
        )
    sq_lines = []
    for sq in sub_questions or []:
        sq_lines.append(
            f"- {sq.get('id')}: {sq.get('question')} (status={sq.get('status')})"
        )
    aspects_text = "\n".join(f"- {a}" for a in aspect_list) or "(未提供，请从问题推断必要方面)"
    evidence_json = json.dumps(_clip_evidence_for_prompt(valid), ensure_ascii=False)

    system = (
        "你在评估检索证据是否足以回答问题。只根据给定证据判断，不要编造未出现的事实。"
        "输出结构化字段：sufficient, covered_aspects, missing_aspects, gaps, reason。"
        "sufficient=true 仅当证据已覆盖回答所需的关键方面；有命中≠充分。"
        "gaps 应可指导下一轮检索 query。"
    )
    human = (
        f"用户问题：{user_question}\n"
        f"{qi_block}"
        f"子问题列表：\n" + ("\n".join(sq_lines) or "(无)") + "\n"
        f"待覆盖方面 aspects：\n{aspects_text}\n"
        f"当前有效证据 JSON：\n{evidence_json}\n"
    )

    usage = None
    try:
        if llm_invoke is not None:
            raw = llm_invoke([("system", system), ("human", human)])
            parsed = _parse_llm_payload(raw)
        else:
            parsed, usage = _invoke_structured_llm(system, human)
    except Exception as exc:  # noqa: BLE001 — degrade to insufficient, keep ReAct alive
        parsed = EvidenceSufficiencyResult(
            sufficient=False,
            covered_aspects=[],
            missing_aspects=aspect_list,
            gaps=["sufficiency LLM 失败，需继续检索或改写"],
            reason=f"llm_error: {type(exc).__name__}",
        )

    out: dict[str, Any] = {
        "precheck": HAS_VALID_EVIDENCE,
        "llm_called": True,
        **parsed.model_dump(),
        "status": "SUFFICIENT" if parsed.sufficient else INSUFFICIENT,
    }
    if usage:
        out["usage"] = usage
    return out


def _invoke_structured_llm(system: str, human: str) -> tuple[EvidenceSufficiencyResult, dict[str, int] | None]:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from app.config import get_settings
    from app.llm import _usage_of, llm_keys_ready

    if not llm_keys_ready():
        return (
            EvidenceSufficiencyResult(
                sufficient=False,
                gaps=["sufficiency LLM unavailable"],
                reason="llm_keys_not_ready",
            ),
            None,
        )

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    messages = [SystemMessage(content=system), HumanMessage(content=human)]
    try:
        structured = model.with_structured_output(EvidenceSufficiencyResult)
        raw = structured.invoke(messages)
        parsed = _parse_llm_payload(raw)
        return parsed, None
    except Exception:
        raw_resp = model.invoke(messages)
        usage = _usage_of(raw_resp)
        parsed = _parse_llm_payload(getattr(raw_resp, "content", raw_resp))
        return parsed, usage


def format_sufficiency_observation(
    result: Mapping[str, Any],
    *,
    qi_id: str | None = None,
    searched_queries: Sequence[str] | None = None,
    rewrite_count: int | None = None,
    rewrite_remaining: int | None = None,
    rewrite_exhausted: bool = False,
) -> str:
    """Compact Observation block for Agent (not a workflow force)."""
    lines = ["[Evidence Sufficiency]"]
    if qi_id:
        lines.append(f"qi_id: {qi_id}")
    lines.append(f"sufficient: {bool(result.get('sufficient'))}")
    lines.append(f"precheck: {result.get('precheck')}")
    if rewrite_count is not None:
        lines.append(f"rewrite_count: {int(rewrite_count)}")
    if rewrite_remaining is not None:
        lines.append(f"rewrite_remaining: {int(rewrite_remaining)}")
    covered = list(result.get("covered_aspects") or [])
    missing = list(result.get("missing_aspects") or [])
    gaps = list(result.get("gaps") or [])
    lines.append("")
    lines.append("covered_aspects:")
    if covered:
        lines.extend(f"- {x}" for x in covered)
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("missing_aspects:")
    if missing:
        lines.extend(f"- {x}" for x in missing)
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("gaps:")
    if gaps:
        lines.extend(f"- {x}" for x in gaps)
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("searched_queries:")
    searched = [str(q).strip() for q in (searched_queries or []) if str(q).strip()]
    if searched:
        lines.extend(f"- {q}" for q in searched[:20])
    else:
        lines.append("- (none)")
    reason = str(result.get("reason") or "").strip()
    if reason:
        lines.append("")
        lines.append(f"reason: {reason}")
    lines.append("")
    if result.get("sufficient"):
        lines.append("instruction: 证据已充分时可整理作答；仍受工具预算与安全限制约束。")
    elif rewrite_exhausted:
        lines.append(
            "instruction: 该 Qi rewrite 额度已用尽，勿再盲目改写补搜；"
            "保留 knowledge_gaps / missing_aspects 作答，禁止伪装已充分。"
        )
    else:
        lines.append(
            "instruction: 优先针对 missing_aspects 或 gaps 生成下一轮检索 Query；"
            "禁止精确重复 searched_queries 中已有 Query；不要仅依据当前证据生成完整结论。"
        )
    return "\n".join(lines)


def assign_evidence_qi_id(
    *,
    query: str,
    sub_questions: Sequence[Mapping[str, Any]] | None,
    explicit_qi_id: str | None = None,
    active_qi_id: str | None = None,
) -> str:
    """Attribution: explicit > active > reliable query match > unassigned."""
    qis = list(sub_questions or [])
    ids = {str(sq.get("id") or "") for sq in qis if sq.get("id")}

    if explicit_qi_id and str(explicit_qi_id) in ids:
        return str(explicit_qi_id)
    if active_qi_id and str(active_qi_id) in ids:
        return str(active_qi_id)

    q = (query or "").strip()
    if q:
        exact = [sq for sq in qis if str(sq.get("question") or "").strip() == q]
        if len(exact) == 1 and exact[0].get("id"):
            return str(exact[0]["id"])
        # Reliable containment only when unique.
        contained = [
            sq
            for sq in qis
            if (text := str(sq.get("question") or "").strip())
            and (text in q or q in text)
            and sq.get("id")
        ]
        if len(contained) == 1:
            return str(contained[0]["id"])

    return "unassigned"
