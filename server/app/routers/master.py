from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.deps import current_user
from app.kb import KnowledgeBaseAccessError, owned_document, resolve_knowledge_base_id
from app.llm import llm_keys_ready
from app.models import Conversation, Document, Entity, EntityLink, KnowledgeBase, Message, User
from app.chains import compare_documents, gather_document_text
from app.ltm import load_ltm_hits
from app.conversation_summary import refresh_conversation_summary
from app.graph import build_graph, initial_state
from app.master import build_master_graph, master_initial_state
from app.chat import _history
from app.tools import search_graph, search_graph_details, search_knowledge, web_search
from app.travel.rate_limit import RateLimitedError
from app.schemas import (
    AgentOut,
    AgentRequest,
    GraphSearchOut,
    GraphSearchDetailOut,
    GraphSearchDocumentOut,
    GraphPathOut,
    GraphDocumentOut,
    CitationOut,
    CompareOut,
    CompareRequest,
    GraphEntityOut,
    GraphLinkOut,
    KnowledgeGraphOut,
)

router = APIRouter(prefix="/api", tags=["master"])


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _load_ready(session: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = owned_document(session, document_id, user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail="文档未完成")
    return doc


@router.post("/compare", response_model=CompareOut)
def compare(body: CompareRequest, session: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.document_id_a == body.document_id_b:
        raise HTTPException(status_code=400, detail="须选择两篇不同文档")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    doc_a = _load_ready(session, body.document_id_a, user.id)
    doc_b = _load_ready(session, body.document_id_b, user.id)
    if doc_a.knowledge_base_id != doc_b.knowledge_base_id:
        raise HTTPException(status_code=400, detail="两篇文档须属于同一知识库")
    text_a = gather_document_text(session, doc_a)
    text_b = gather_document_text(session, doc_b)
    if not text_a or not text_b:
        raise HTTPException(status_code=400, detail="empty_content")
    comparison = compare_documents(text_a, doc_a.filename, text_b, doc_b.filename)
    return CompareOut(
        document_id_a=doc_a.id,
        document_id_b=doc_b.id,
        comparison=comparison,
    )


def _agent_prepare(
    body: AgentRequest, session: Session, user_id: uuid.UUID
) -> tuple[str, uuid.UUID, Conversation, list[dict[str, str]], str, list]:
    """解析/创建会话与上下文；stream 与非 stream 共用。"""
    if body.task not in ("agent", "report"):
        raise HTTPException(status_code=400, detail="task 须为 agent 或 report")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    try:
        kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id, user_id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if body.conversation_id is None:
        convo = Conversation(user_id=user_id, knowledge_base_id=kb_id, title=body.query[:40])
        session.add(convo)
        session.flush()
        history_msgs: list[dict[str, str]] = []
        summary_text = ""
    else:
        convo = session.get(Conversation, body.conversation_id)
        if convo is None or convo.user_id != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        history_msgs = [{"role": role, "content": content} for role, content in _history(session, convo.id)]
        summary_text = (convo.summary or "").strip()
    ltm_hits = load_ltm_hits(session, user_id)
    task = "report" if body.task == "report" else "agent"
    return task, kb_id, convo, history_msgs, summary_text, ltm_hits


def _agent_persist(
    session: Session,
    task: str,
    kb_id: uuid.UUID,
    convo: Conversation,
    body: AgentRequest,
    out: dict,
) -> AgentOut:
    """把 Master 输出落消息/摘要并组装 AgentOut。"""
    answer = out.get("answer") or ""
    cites = [CitationOut.model_validate(item) for item in (out.get("citations") or [])]
    session.add(Message(conversation_id=convo.id, role="user", content=body.query, citations=None))
    session.add(
        Message(
            conversation_id=convo.id,
            role="assistant",
            content=answer,
            citations=[c.model_dump(mode="json") for c in cites] or None,
        )
    )
    refresh_conversation_summary(session, convo.id)
    session.commit()
    session.refresh(convo)
    return AgentOut(
        task=task,
        knowledge_base_id=kb_id,
        conversation_id=convo.id,
        answer=answer,
        citations=cites,
        loop_count=int(out.get("loop_count") or 0),
        intent=str(out.get("intent") or "") or None,
        report_url=out.get("report_url"),
        pending_action=out.get("pending_action"),
        bookings=list(out.get("bookings") or []) or None,
    )




def _load_last_pending_action(conversation_id: uuid.UUID) -> dict[str, Any] | None:
    """从 Master 同 thread checkpoint 读取上一次的 pending_action（供 HITL 确认）。"""
    try:
        graph = build_master_graph()
        snapshot = graph.get_state({"configurable": {"thread_id": f"master-{conversation_id}"}})
        if snapshot and snapshot.values:
            return snapshot.values.get("pending_action")
    except Exception:
        pass
    return None

def _master_state_config(body, task, convo, history_msgs, summary_text, ltm_hits):
    pending_action = None
    if body.hitl_confirm is not None and body.conversation_id:
        pending_action = _load_last_pending_action(body.conversation_id)
    state = master_initial_state(
        body.query,
        task=task,
        knowledge_base_id=body.knowledge_base_id,
        conversation_id=convo.id,
        history=history_msgs,
        summary=summary_text,
        ltm_hits=ltm_hits,
        allow_web=bool(body.allow_web),
        pending_action=pending_action,
        hitl_confirm=body.hitl_confirm,
    )
    configurable = {
        "thread_id": f"master-{convo.id}",
        "session": None,
        "user_id": None,
    }
    return state, configurable


def _agent_out(body: AgentRequest, session: Session, user_id: uuid.UUID) -> AgentOut:
    task, kb_id, convo, history_msgs, summary_text, ltm_hits = _agent_prepare(body, session, user_id)
    state, configurable = _master_state_config(body, task, convo, history_msgs, summary_text, ltm_hits)
    configurable["session"] = session
    configurable["user_id"] = user_id
    try:
        out = build_master_graph().invoke(state, config={"configurable": configurable})
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return _agent_persist(session, task, kb_id, convo, body, out)


@router.post("/agent", response_model=AgentOut)
def agent_run(body: AgentRequest, session: Session = Depends(get_db), user: User = Depends(current_user)):
    return _agent_out(body, session, user.id)


@router.post("/agent/stream")
async def agent_stream(
    body: AgentRequest, request: Request, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    """事件序列：intent →（progress / travel_data / plan_html，plan 路径）→ token 逐字 → citations 终态。

    伪流式：图在响应前同步跑完（沿用既有设计），但事件顺序与真实 Hook 一致；
    plan 子 Agent 执行中的 progress/travel_data/plan_html 经 emit 回调按发生顺序收集。
    """
    task, kb_id, convo, history_msgs, summary_text, ltm_hits = _agent_prepare(body, session, user.id)
    state, configurable = _master_state_config(body, task, convo, history_msgs, summary_text, ltm_hits)
    configurable["session"] = session
    configurable["user_id"] = user.id
    hook_events: list[dict] = []

    def emit(event: dict) -> None:
        hook_events.append(event)

    configurable["emit"] = emit
    final: dict = dict(state)
    try:
        stream_iter = build_master_graph().stream(
            state, config={"configurable": configurable}, stream_mode="updates"
        )
    except RateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    for chunk in stream_iter:
        for node, updates in chunk.items():
            if not isinstance(updates, dict):
                continue
            final.update(updates)
            if node == "intent" and updates.get("intent"):
                emit({"type": "intent", "intent": updates["intent"]})
    result = _agent_persist(session, task, kb_id, convo, body, final)

    async def events():
        for event in hook_events:
            if await request.is_disconnected():
                return
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        for char in result.answer:
            if await request.is_disconnected():
                return
            yield f"data: {json.dumps({'type': 'token', 'text': char}, ensure_ascii=False)}\n\n"
        payload = {"type": "citations", **result.model_dump(mode="json")}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/agent/trace")
async def agent_trace(
    body: AgentRequest, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    """旁路调试：逐节点推送 Agent 图执行轨迹。不落库，不影响 /api/agent 与 /api/agent/stream。"""
    if body.task not in ("agent", "report"):
        raise HTTPException(status_code=400, detail="task 须为 agent 或 report")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    try:
        kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id, user.id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task = "report" if body.task == "report" else "agent"
    state = initial_state(
        body.query,
        knowledge_base_id=kb_id,
        task=task,
        history=[],
        summary="",
        ltm_hits=load_ltm_hits(session, user.id),
        allow_web=bool(body.allow_web),
    )
    config = {
        "configurable": {
            "thread_id": f"trace-{uuid.uuid4()}",
            "session": session,
            "user_id": user.id,
        }
    }

    def events():
        final: dict = dict(state)
        last_ts = time.monotonic()
        token_sum = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for chunk in build_graph().stream(state, config=config, stream_mode="updates"):
            now = time.monotonic()
            elapsed_ms = int((now - last_ts) * 1000)
            last_ts = now
            for node, updates in chunk.items():
                if not isinstance(updates, dict):
                    continue
                final.update(updates)
                event: dict[str, object] = {"type": "step", "node": node, "elapsed_ms": elapsed_ms}
                usage = updates.get("usage")
                if isinstance(usage, dict):
                    event["tokens"] = usage
                    for key in token_sum:
                        token_sum[key] += int(usage.get(key) or 0)
                if node == "reason":
                    event["action"] = str(updates.get("next_action") or "")
                    event["query"] = str(updates.get("search_query") or "")
                    if updates.get("subtasks"):
                        event["subtasks"] = list(updates["subtasks"])
                elif node == "run_tool":
                    action = final.get("next_action")
                    if action == "web" or "web_hits" in updates:
                        event["tool"] = "web_search"
                        event["hits"] = len(updates.get("web_hits") or [])
                    elif action == "graph":
                        event["tool"] = "search_graph"
                        event["hits"] = len(updates.get("citations") or [])
                    else:
                        event["tool"] = "search_knowledge"
                        event["hits"] = len(updates.get("citations") or [])
                    event["query"] = str(final.get("search_query") or "")
                elif node == "generate":
                    event["answer_len"] = len(str(updates.get("answer") or ""))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        cites = [CitationOut.model_validate(item) for item in (final.get("citations") or [])]
        payload = {
            "type": "final",
            "task": task,
            "knowledge_base_id": str(kb_id) if kb_id else None,
            "answer": str(final.get("answer") or ""),
            "citations": [c.model_dump(mode="json") for c in cites],
            "loop_count": int(final.get("loop_count") or 0),
            "tokens": dict(token_sum),
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


def _graph_out(entities: list[Entity], links: list[EntityLink]) -> KnowledgeGraphOut:
    doc_counts: dict[uuid.UUID, set[uuid.UUID | None]] = {row.id: set() for row in entities}
    for link in links:
        doc_counts.get(link.from_id, set()).add(link.document_id)
        doc_counts.get(link.to_id, set()).add(link.document_id)
    return KnowledgeGraphOut(
        entities=[
            GraphEntityOut(
                id=row.id,
                name=row.name,
                type=row.type,
                created_at=row.created_at,
                source_doc_count=len(doc_counts.get(row.id, set())),
            )
            for row in entities
        ],
        links=[
            GraphLinkOut(from_id=row.from_id, to_id=row.to_id, rel=row.rel, document_id=row.document_id)
            for row in links
        ],
    )




@router.get("/graph/search", response_model=list[GraphSearchOut])
def search_graph_endpoint(
    query: str,
    knowledge_base_id: uuid.UUID,
    k: int = 5,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """基于知识图谱的检索：按 query 匹配实体并沿关系扩展，返回相关文档切片。"""
    if k < 1 or k > 20:
        raise HTTPException(status_code=400, detail="k 须在 1–20 之间")
    kb = session.get(KnowledgeBase, knowledge_base_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    hits = search_graph(session, query, user.id, knowledge_base_id, k=k)
    return [
        GraphSearchOut(
            document_id=hit.document_id,
            document_name=hit.document_name,
            chunk_id=hit.chunk_id,
            content=hit.content,
            score=hit.score,
            page=hit.page,
            heading=hit.heading,
            kind=hit.kind,
        )
        for hit in hits
    ]


@router.get("/graph/search/details", response_model=GraphSearchDetailOut)
def search_graph_details_endpoint(
    query: str,
    knowledge_base_id: uuid.UUID,
    k: int = 5,
    depth: int = 2,
    rel: str | None = None,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """知识图谱检索详情页：返回命中实体、关系、路径与相关文档。"""
    if k < 1 or k > 20:
        raise HTTPException(status_code=400, detail="k 须在 1–20 之间")
    if depth < 1 or depth > 3:
        raise HTTPException(status_code=400, detail="depth 须在 1–3 之间")
    kb = session.get(KnowledgeBase, knowledge_base_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    raw = search_graph_details(session, query, user.id, knowledge_base_id, k=k, max_hops=depth, rel=rel)
    entity_map = {row.id: GraphEntityOut(
        id=row.id, name=row.name, type=row.type, created_at=row.created_at,
        source_doc_count=sum(1 for link in raw["links"] if link.from_id == row.id or link.to_id == row.id),
    ) for row in raw["entities"]}
    return GraphSearchDetailOut(
        query=raw["query"],
        entities=list(entity_map.values()),
        links=[GraphLinkOut(from_id=link.from_id, to_id=link.to_id, rel=link.rel, document_id=link.document_id) for link in raw["links"]],
        documents=[GraphSearchDocumentOut(**doc) for doc in raw["documents"]],
        paths=[GraphPathOut(
            entities=[entity_map[link.from_id] for link in path] + [entity_map[path[-1].to_id]],
            rels=[link.rel for link in path],
        ) for path in raw["paths"] if all(link.from_id in entity_map and link.to_id in entity_map for link in path)],
    )


@router.get("/graph/documents", response_model=list[GraphDocumentOut])
def get_graph_documents(
    ids: list[uuid.UUID] = Query(default_factory=list),
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """批量查询图谱中实体/关系来源的文档元数据。"""
    if not ids:
        return []
    rows = session.scalars(select(Document).where(Document.id.in_(ids), Document.status == "ready")).all()
    # 权限校验：只返回用户自己的文档
    allowed_ids = {row.id for row in rows if row.knowledge_base.user_id == user.id}
    return [GraphDocumentOut(document_id=row.id, document_name=row.filename, version=row.version) for row in rows if row.id in allowed_ids]


@router.get("/graph", response_model=KnowledgeGraphOut)
def get_graph(
    knowledge_base_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        kb_id = resolve_knowledge_base_id(session, knowledge_base_id, user.id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if document_id is not None:
        doc = owned_document(session, document_id, user.id)
        if doc is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if doc.knowledge_base_id != kb_id:
            return _graph_out([], [])
        link_rows = list(session.scalars(select(EntityLink).where(EntityLink.document_id == document_id)))
        ids = {row.from_id for row in link_rows} | {row.to_id for row in link_rows}
        entity_rows: list[Entity] = []
        if ids:
            entity_rows = list(
                session.scalars(select(Entity).where(Entity.id.in_(ids), Entity.knowledge_base_id == kb_id))
            )
        allowed = {row.id for row in entity_rows}
        link_rows = [row for row in link_rows if row.from_id in allowed and row.to_id in allowed]
        return _graph_out(entity_rows, link_rows)
    entity_rows = list(session.scalars(select(Entity).where(Entity.knowledge_base_id == kb_id)))
    ids = {row.id for row in entity_rows}
    link_rows: list[EntityLink] = []
    if ids:
        link_rows = list(session.scalars(select(EntityLink).where(EntityLink.from_id.in_(ids))))
    return _graph_out(entity_rows, link_rows)
