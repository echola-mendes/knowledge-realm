"""ReAct tool-round Evidence + Sufficiency post-process (not a LangGraph node)."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from app.agent.evidence_merge import merge_evidence
from app.agent.evidence_sufficiency import (
    assign_evidence_qi_id,
    evaluate_evidence_sufficiency,
    format_sufficiency_observation,
)
from app.agent.rewrite import MAX_REWRITE_PER_Q
from app.agent.sufficiency import INSUFFICIENT, SUFFICIENT


def _parse_payload(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"text": text}
    return data if isinstance(data, dict) else {"text": text}


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else str(content or "")


def citation_to_evidence(cite: Mapping[str, Any], *, qi_id: str | None = None) -> dict[str, Any]:
    eid = str(cite.get("chunk_id") or cite.get("id") or "").strip()
    item: dict[str, Any] = {
        "id": eid,
        "document_id": str(cite.get("document_id") or ""),
        "document_name": cite.get("document_name"),
        "chunk_id": eid,
        "parent_id": str(cite["parent_id"]) if cite.get("parent_id") is not None else None,
        "score": float(cite.get("score") or 0.0),
        "content": str(cite.get("content") or ""),
        "related_questions": [],
    }
    if qi_id is not None:
        item["qi_id"] = qi_id
    return item


def web_hit_to_evidence(hit: Mapping[str, Any], *, qi_id: str | None = None) -> dict[str, Any]:
    url = str(hit.get("url") or "").strip()
    eid = url or str(hit.get("title") or hit.get("id") or "").strip()
    content = str(hit.get("snippet") or hit.get("content") or "").strip()
    item: dict[str, Any] = {
        "id": eid,
        "document_id": url,
        "document_name": hit.get("title") or url,
        "chunk_id": eid,
        "parent_id": None,
        "score": float(hit.get("score") or 0.0),
        "content": content,
        "related_questions": [],
    }
    if qi_id is not None:
        item["qi_id"] = qi_id
    return item


def infer_active_qi_id(sub_questions: Sequence[Mapping[str, Any]] | None) -> str | None:
    open_qis = [
        sq
        for sq in (sub_questions or [])
        if str(sq.get("status") or "") != SUFFICIENT and sq.get("id")
    ]
    if len(open_qis) == 1:
        return str(open_qis[0]["id"])
    return None


def _tool_call_args_by_id(ai_message: AIMessage | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if ai_message is None:
        return out
    for tc in list(getattr(ai_message, "tool_calls", None) or []):
        tc_id = str(tc.get("id") or "")
        args = tc.get("args") or {}
        if tc_id and isinstance(args, dict):
            out[tc_id] = args
    return out


def _patch_tool_message(
    msg: ToolMessage,
    sufficiency: Mapping[str, Any],
    *,
    qi_id: str | None,
    searched_queries: Sequence[str] | None = None,
    rewrite_count: int = 0,
    rewrite_remaining: int = 0,
    rewrite_exhausted: bool = False,
) -> ToolMessage:
    payload = _parse_payload(_message_text(msg))
    searched = [str(q).strip() for q in (searched_queries or []) if str(q).strip()]
    summary = {
        "sufficient": bool(sufficiency.get("sufficient")),
        "precheck": sufficiency.get("precheck"),
        "covered_aspects": list(sufficiency.get("covered_aspects") or []),
        "missing_aspects": list(sufficiency.get("missing_aspects") or []),
        "gaps": list(sufficiency.get("gaps") or []),
        "reason": sufficiency.get("reason") or "",
        "qi_id": qi_id,
        "searched_queries": searched,
        "rewrite_count": int(rewrite_count),
        "rewrite_remaining": int(rewrite_remaining),
    }
    payload["sufficiency"] = summary
    payload["sufficiency_text"] = format_sufficiency_observation(
        sufficiency,
        qi_id=qi_id,
        searched_queries=searched,
        rewrite_count=int(rewrite_count),
        rewrite_remaining=int(rewrite_remaining),
        rewrite_exhausted=rewrite_exhausted,
    )
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=getattr(msg, "tool_call_id", "") or "",
        name=getattr(msg, "name", None),
        id=getattr(msg, "id", None),
    )


def process_react_tool_round(
    state: Mapping[str, Any],
    tool_messages: Sequence[AnyMessage],
    *,
    ai_message: AIMessage | None = None,
    user_question: str = "",
    llm_invoke=None,
) -> dict[str, Any]:
    """Build evidence, run precheck(+LLM), update Qi/gaps, patch ToolMessages."""
    sub_questions = [dict(sq) for sq in (state.get("sub_questions") or [])]
    pool = [dict(e) for e in (state.get("evidence") or [])]
    searched = list(state.get("searched_queries") or [])
    args_by_id = _tool_call_args_by_id(ai_message)
    active = infer_active_qi_id(sub_questions)

    round_items: list[dict[str, Any]] = []
    primary_qi: str | None = None
    for msg in tool_messages:
        if not isinstance(msg, ToolMessage):
            continue
        payload = _parse_payload(_message_text(msg))
        tc_id = str(getattr(msg, "tool_call_id", "") or "")
        args = args_by_id.get(tc_id) or {}
        query = str(args.get("query") or "").strip()
        explicit = args.get("qi_id")
        explicit_s = str(explicit).strip() if explicit is not None else None
        qi_id = assign_evidence_qi_id(
            query=query,
            sub_questions=sub_questions,
            explicit_qi_id=explicit_s,
            active_qi_id=active,
        )
        if primary_qi is None and qi_id != "unassigned":
            primary_qi = qi_id
        if query and query not in searched:
            searched.append(query)

        for cite in payload.get("citations") or []:
            if isinstance(cite, dict):
                round_items.append(citation_to_evidence(cite, qi_id=qi_id))
        for hit in payload.get("web_hits") or []:
            if isinstance(hit, dict):
                round_items.append(web_hit_to_evidence(hit, qi_id=qi_id))

        # rewrite_count when query is a rewrite relative to matched Qi
        if qi_id != "unassigned" and query:
            for sq in sub_questions:
                if str(sq.get("id")) != qi_id:
                    continue
                q_text = str(sq.get("question") or "").strip()
                prior_ids = list(sq.get("evidence_ids") or [])
                if q_text and query != q_text and prior_ids:
                    rc = int(sq.get("rewrite_count") or 0)
                    if rc < MAX_REWRITE_PER_Q:
                        sq["rewrite_count"] = rc + 1
                    elif rc >= MAX_REWRITE_PER_Q:
                        # note in gaps later via sufficiency
                        pass
                break

    merged_round = merge_evidence(pool + round_items)
    evidence = list(merged_round["merged"])

    # Refresh evidence_ids on each Qi from pool
    by_qi: dict[str, list[str]] = {}
    for item in evidence:
        qid = str(item.get("qi_id") or "unassigned")
        eid = str(item.get("id") or item.get("chunk_id") or "")
        if not eid:
            continue
        by_qi.setdefault(qid, [])
        if eid not in by_qi[qid]:
            by_qi[qid].append(eid)
    for sq in sub_questions:
        sq["evidence_ids"] = list(by_qi.get(str(sq.get("id")), []))

    focus_qi = None
    if primary_qi:
        focus_qi = next((sq for sq in sub_questions if str(sq.get("id")) == primary_qi), None)
    focus_evidence = (
        [e for e in evidence if str(e.get("qi_id") or "") == primary_qi]
        if primary_qi
        else list(round_items) or evidence
    )
    if not focus_evidence:
        focus_evidence = evidence

    sufficiency = evaluate_evidence_sufficiency(
        user_question=user_question or "",
        evidence=focus_evidence,
        sub_questions=sub_questions,
        qi=focus_qi,
        llm_invoke=llm_invoke,
    )

    gaps = list(sufficiency.get("gaps") or [])
    missing = list(sufficiency.get("missing_aspects") or [])
    for m in missing:
        note = f"missing_aspect: {m}"
        if note not in gaps:
            gaps.append(note)

    # Cap note when rewrite exhausted on focus qi
    if focus_qi is not None and int(focus_qi.get("rewrite_count") or 0) >= MAX_REWRITE_PER_Q:
        note = f"qi {focus_qi.get('id')}: rewrite budget exhausted"
        if note not in gaps:
            gaps.append(note)

    status = SUFFICIENT if sufficiency.get("sufficient") else INSUFFICIENT
    if focus_qi is not None:
        focus_qi["status"] = status
        focus_qi["sufficiency"] = {
            "sufficient": bool(sufficiency.get("sufficient")),
            "covered_aspects": list(sufficiency.get("covered_aspects") or []),
            "missing_aspects": list(sufficiency.get("missing_aspects") or []),
            "gaps": list(sufficiency.get("gaps") or []),
            "reason": sufficiency.get("reason") or "",
            "precheck": sufficiency.get("precheck"),
        }
        # write back into list
        for i, sq in enumerate(sub_questions):
            if str(sq.get("id")) == str(focus_qi.get("id")):
                sub_questions[i] = focus_qi
                break

    rewrite_count = int(focus_qi.get("rewrite_count") or 0) if focus_qi is not None else 0
    rewrite_remaining = max(0, MAX_REWRITE_PER_Q - rewrite_count)
    rewrite_exhausted = focus_qi is not None and rewrite_count >= MAX_REWRITE_PER_Q

    patched: list[AnyMessage] = []
    for msg in tool_messages:
        if isinstance(msg, ToolMessage):
            patched.append(
                _patch_tool_message(
                    msg,
                    sufficiency,
                    qi_id=primary_qi,
                    searched_queries=searched,
                    rewrite_count=rewrite_count,
                    rewrite_remaining=rewrite_remaining,
                    rewrite_exhausted=rewrite_exhausted,
                )
            )
        else:
            patched.append(msg)

    updates: dict[str, Any] = {
        "agent_messages": patched,
        "evidence": evidence,
        "sub_questions": sub_questions,
        "knowledge_gaps": gaps,
        "searched_queries": searched,
        "sufficiency": {
            "sufficient": bool(sufficiency.get("sufficient")),
            "precheck": sufficiency.get("precheck"),
            "qi_id": primary_qi,
            "covered_aspects": list(sufficiency.get("covered_aspects") or []),
            "missing_aspects": list(sufficiency.get("missing_aspects") or []),
            "gaps": list(sufficiency.get("gaps") or []),
            "reason": sufficiency.get("reason") or "",
            "llm_called": bool(sufficiency.get("llm_called")),
            "rewrite_count": rewrite_count,
            "rewrite_remaining": rewrite_remaining,
        },
    }
    usage = sufficiency.get("usage")
    if isinstance(usage, dict):
        updates["usage"] = usage
    return updates
