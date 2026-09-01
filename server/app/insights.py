from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import llm_keys_ready
from app.models import Document, DocumentTag, KnowledgeBase, RetrievalLabel, Tag

MAX_DOCS = 30


def _chat_complete(system: str, human: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    result = model.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    return str(result.content).strip()


def _build_doc_input(docs: list[Document]) -> tuple[str, bool]:
    truncated = len(docs) > MAX_DOCS
    selected = docs[:MAX_DOCS]
    lines: list[str] = []
    for doc in selected:
        summary = (doc.summary or "").strip()
        lines.append(f"- 文档名：{doc.filename}\n  摘要：{summary}")
    return "\n\n".join(lines), truncated


def analyze_conflicts(docs: list[Document]) -> dict[str, Any]:
    """对知识库内文档做冲突检测。输入文档清单（filename+summary），输出结构化冲突报告。"""
    if not llm_keys_ready():
        raise RuntimeError("未配置 LLM API Key")
    if not docs:
        return {"conflicts": [], "truncated": False}

    body, truncated = _build_doc_input(docs)
    system = (
        "你是一位知识库审计员。请根据下方文档清单，检测不同文档之间对同一事实的表述矛盾。"
        "只输出 JSON 对象，不要其它文字。格式："
        '{"conflicts":[{"documents":["文档A","文档B"],"point":"矛盾点","detail":"具体差异","suggestion":"建议"}]}。'
        "如果没有发现矛盾，返回 {\"conflicts\":[]}。"
    )
    raw = _chat_complete(system, body)
    conflicts: list[dict[str, Any]] = []
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
        if isinstance(parsed, dict):
            for item in parsed.get("conflicts") or []:
                if not isinstance(item, dict):
                    continue
                docs_field = item.get("documents") or []
                if not isinstance(docs_field, list):
                    docs_field = []
                conflicts.append({
                    "documents": [str(d).strip() for d in docs_field if str(d).strip()],
                    "point": str(item.get("point") or "").strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "suggestion": str(item.get("suggestion") or "").strip(),
                })
    except json.JSONDecodeError:
        conflicts = []
    return {"conflicts": conflicts, "truncated": truncated}


def analyze_gaps(docs: list[Document], weak: list[str]) -> dict[str, Any]:
    """知识缺口分析：覆盖主题 + 缺口建议；weak 为低命中提问佐证（可空，无则省略）。"""
    if not llm_keys_ready():
        raise RuntimeError("未配置 LLM API Key")
    if not docs:
        return {"covered_topics": [], "gaps": [], "truncated": False}

    body, truncated = _build_doc_input(docs)
    if weak:
        human = f"{body}\n\n【低命中提问】\n" + "\n".join(f"- {q}" for q in weak)
        evidence_rule = "gaps.evidence 必须引用【低命中提问】中的原句。"
    else:
        human = body
        evidence_rule = "没有低命中提问，gaps.evidence 必须为空字符串。"
    system = (
        "你是知识库规划师。根据文档清单推断已覆盖主题与缺失主题。"
        "只输出 JSON 对象，不要其它文字。格式："
        '{"covered_topics":["主题1"],"gaps":[{"topic":"缺失主题","evidence":"依据","suggestion":"建议补充的资料"}]}。'
        "禁止编造清单里没有的文档。"
        f"{evidence_rule}"
    )
    raw = _chat_complete(system, human)
    covered: list[str] = []
    gaps: list[dict[str, Any]] = []
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = json.loads(raw[start : end + 1] if start >= 0 and end >= start else raw)
        if isinstance(parsed, dict):
            covered = [str(t).strip() for t in (parsed.get("covered_topics") or []) if str(t).strip()]
            for item in parsed.get("gaps") or []:
                if not isinstance(item, dict):
                    continue
                gaps.append({
                    "topic": str(item.get("topic") or "").strip(),
                    "evidence": str(item.get("evidence") or "").strip(),
                    "suggestion": str(item.get("suggestion") or "").strip(),
                })
    except json.JSONDecodeError:
        covered, gaps = [], []
    if not weak:
        for item in gaps:
            item["evidence"] = ""
    return {"covered_topics": covered, "gaps": gaps, "truncated": truncated}


def weak_queries(session: Session, user_id: uuid.UUID, limit: int = 10) -> list[str]:
    """retrieval_label 中 relevance<=1 的去重查询词。"""
    rows = session.execute(
        select(RetrievalLabel.query_norm)
        .where(RetrievalLabel.user_id == user_id, RetrievalLabel.relevance <= 1)
        .distinct()
        .limit(limit)
    ).all()
    return [r[0] for r in rows if r[0]]


def _ensure_tags(session: Session, user_id: uuid.UUID, doc: Document, names: list[str]) -> list[str]:
    """落 tag + document_tag（幂等），返回实际新打的标签名。"""
    from app.chains import suggest_tag_names  # noqa: F401  语义参考

    applied: list[str] = []
    for name in names[:3]:
        name = name.strip()
        if not name or len(name) > 100:
            continue
        tag = session.scalar(select(Tag).where(Tag.user_id == user_id, Tag.name == name))
        if tag is None:
            tag = Tag(user_id=user_id, name=name)
            session.add(tag)
            session.flush()
        exists = session.scalar(
            select(DocumentTag).where(DocumentTag.document_id == doc.id, DocumentTag.tag_id == tag.id)
        )
        if exists is None:
            session.add(DocumentTag(document_id=doc.id, tag_id=tag.id))
            applied.append(name)
    session.commit()
    return applied


def organize_kb(session: Session, kb: KnowledgeBase, *, apply_tags: bool = True) -> dict[str, Any]:
    """自动整理：无标签文档补标签（apply_tags=true 直接落库）；报告疑似重复/空摘要/命名问题。"""
    docs = list(
        session.scalars(select(Document).where(Document.knowledge_base_id == kb.id).order_by(Document.created_at)).all()
    )
    tagged_ids: set[uuid.UUID] = set()
    if docs:
        tagged_ids = set(
            session.scalars(
                select(DocumentTag.document_id).where(DocumentTag.document_id.in_([d.id for d in docs]))
            ).all()
        )
    untagged = [d for d in docs if d.id not in tagged_ids][:MAX_DOCS]

    applied: list[dict[str, Any]] = []
    if llm_keys_ready():
        from app.chains import suggest_tag_names

        for doc in untagged:
            text = (doc.summary or "").strip() or doc.filename
            try:
                names = suggest_tag_names(text)
            except Exception:  # noqa: BLE001
                continue
            if not names:
                continue
            if apply_tags:
                used = _ensure_tags(session, kb.user_id, doc, names)
                if used:
                    applied.append({"document": doc.filename, "tags": used})
            else:
                applied.append({"document": doc.filename, "tags": names[:3]})

    by_name: dict[str, list[str]] = {}
    empty_summary: list[str] = []
    bad_names: list[str] = []
    for doc in docs:
        base = doc.filename.rsplit(".", 1)[0] if "." in doc.filename else doc.filename
        by_name.setdefault(base.lower(), []).append(doc.filename)
        if not (doc.summary or "").strip():
            empty_summary.append(doc.filename)
        if doc.kind not in ("url", "note") and len(base.strip()) <= 2:
            bad_names.append(doc.filename)
    name_dups = [names for names in by_name.values() if len(names) > 1]

    checksum_dups: list[list[str]] = []
    current_checksums = {d.checksum for d in docs if d.checksum}
    if current_checksums:
        rows = session.execute(
            select(Document.filename, Document.checksum)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(KnowledgeBase.user_id == kb.user_id, Document.checksum.in_(current_checksums))
            .order_by(Document.checksum, Document.created_at)
        ).all()
        groups: dict[str, list[str]] = {}
        for filename, checksum in rows:
            if not filename or not checksum:
                continue
            groups.setdefault(checksum, []).append(filename)
        seen_groups: set[tuple[str, ...]] = set()
        for group in groups.values():
            if len(group) > 1:
                sig = tuple(sorted(group))
                if sig not in seen_groups:
                    seen_groups.add(sig)
                    checksum_dups.append(group)

    return {
        "applied": applied,
        "duplicates": name_dups + checksum_dups,
        "empty_summary": empty_summary,
        "bad_names": bad_names,
        "untagged_total": len(untagged),
        "applied_tags": apply_tags,
    }
