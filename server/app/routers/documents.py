from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.deps import current_user
from app.kb import KnowledgeBaseAccessError, owned_document, resolve_knowledge_base_id
from app.llm import llm_keys_ready
from app.models import Document, DocumentChunk, DocumentTag, Entity, EntityLink, Favorite, KnowledgeBase, Tag, User
from app.p1.chains import extract_graph, gather_document_text, suggest_tag_names, summarize_document
from app.schemas import (
    DocumentChunkOut,
    DocumentGraphOut,
    DocumentOut,
    DocumentTagsPut,
    GraphEntityOut,
    GraphLinkOut,
    NoteCreate,
    RelatedDocumentOut,
    UrlCreate,
)
from app.chunk import CHUNK_OVERLAP, CHUNK_SIZE, split_markdown
from app import index as index_mod
from app.index import STATUS_INDEXING
from app.es_bm25 import EsNotConfiguredError, delete_document_chunks
from app.search import search_chunks
from app.storage import original_path, parsed_dir, remove_document_files, write_original

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".markdown": "md", ".txt": "txt"}
UPLOAD_MAX_BYTES = 100 * 1024 * 1024
STATUS_PENDING = "pending"
NOTE_FILENAME_MAX = 80


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _note_filename_from_content(text: str) -> str:
    """从正文首个 Markdown 标题或首行生成文件名；无则「笔记.md」。"""
    title = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
        else:
            title = stripped
        break
    if not title:
        return "笔记.md"
    for ch in '<>:"/\\|?*':
        title = title.replace(ch, "")
    title = " ".join(title.split()).strip(" .")
    if not title:
        return "笔记.md"
    if len(title) > NOTE_FILENAME_MAX:
        title = title[:NOTE_FILENAME_MAX].rstrip()
    if not title.lower().endswith(".md"):
        title = f"{title}.md"
    return title


def _normalize_ext(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _owned_doc(session: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    doc = owned_document(session, document_id, user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


def _document_out(doc: Document, session: Session, user_id: uuid.UUID, *, existed: bool = False) -> DocumentOut:
    tag_ids = list(session.scalars(select(DocumentTag.tag_id).where(DocumentTag.document_id == doc.id)))
    fav = session.get(Favorite, (user_id, doc.id)) is not None
    kb = session.get(KnowledgeBase, doc.knowledge_base_id)
    owner = session.get(User, kb.user_id) if kb else None
    return DocumentOut.model_validate(doc).model_copy(
        update={
            "existed": existed,
            "source_url": doc.source_url,
            "source_path": str(original_path(doc.id, doc.ext)),
            "tag_ids": tag_ids,
            "is_favorite": fav,
            "created_by": owner.username if owner else "",
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
        }
    )


def _chunks_for_document(doc: Document, session: Session) -> list[DocumentChunkOut]:
    rows = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    if rows:
        return [
            DocumentChunkOut(
                id=c.id,
                chunk_index=c.chunk_index,
                chunk_label=c.chunk_label,
                content=c.content,
                page=c.page,
                heading=c.heading,
                vector_status="ready",
                created_at=c.created_at,
            )
            for c in rows
        ]
    md_path = parsed_dir(doc.id) / "document.md"
    if not md_path.is_file():
        return []
    pieces = split_markdown(md_path.read_text(encoding="utf-8"))
    vector_status = "indexing" if doc.status == STATUS_INDEXING else "pending"
    return [
        DocumentChunkOut(
            chunk_index=i,
            content=piece.content,
            page=piece.page,
            heading=piece.heading,
            vector_status=vector_status,
        )
        for i, piece in enumerate(pieces)
    ]


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: uuid.UUID | None = Form(None),
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ext = _normalize_ext(file.filename or "")
    if ext not in ALLOWED:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    data = await file.read()
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 100MB")
    try:
        kb_id = resolve_knowledge_base_id(session, knowledge_base_id, user.id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    checksum = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, session, user.id, existed=True)
    doc_id = uuid.uuid4()
    write_original(doc_id, ext, data)
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=file.filename or f"upload{ext}",
        ext=ext,
        kind=ALLOWED[ext],
        checksum=checksum,
        status=STATUS_PENDING,
        byte_size=len(data),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(index_mod.process_document, doc.id)
    return _document_out(doc, session, user.id, existed=False)


@router.post("/notes", response_model=DocumentOut)
def create_note(
    body: NoteCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="笔记内容为空")
    try:
        kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id, user.id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = text.encode("utf-8")
    checksum = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, session, user.id, existed=True)
    doc_id = uuid.uuid4()
    write_original(doc_id, ".md", data)
    name = (body.filename or "").strip() or _note_filename_from_content(text)
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=name,
        ext=".md",
        kind="note",
        checksum=checksum,
        status=STATUS_PENDING,
        byte_size=len(data),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(index_mod.process_document, doc.id)
    return _document_out(doc, session, user.id, existed=False)


@router.post("/url", response_model=DocumentOut)
def create_url_document(
    body: UrlCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="只支持 http/https 公开页")
    try:
        kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id, user.id)
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    checksum = hashlib.sha256(url.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, session, user.id, existed=True)
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=url,
        ext=".md",
        kind="url",
        source_url=url,
        checksum=checksum,
        status=STATUS_PENDING,
        byte_size=0,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    background.add_task(index_mod.process_document, doc.id)
    return _document_out(doc, session, user.id, existed=False)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    favorite: bool | None = None,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if knowledge_base_id is not None:
        try:
            kb_id = resolve_knowledge_base_id(session, knowledge_base_id, user.id)
        except KnowledgeBaseAccessError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        stmt = select(Document).where(Document.knowledge_base_id == kb_id)
    else:
        stmt = (
            select(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(KnowledgeBase.user_id == user.id)
        )
    if tag_id is not None:
        tag = session.get(Tag, tag_id)
        if tag is None or tag.user_id != user.id:
            raise HTTPException(status_code=404, detail="标签不存在")
        stmt = stmt.join(DocumentTag).where(DocumentTag.tag_id == tag_id)
    if favorite is True:
        stmt = stmt.join(Favorite, Favorite.document_id == Document.id).where(Favorite.user_id == user.id)
    rows = session.scalars(stmt.order_by(Document.created_at.desc())).all()
    return [_document_out(row, session, user.id) for row in rows]


@router.put("/{document_id}/tags", response_model=DocumentOut)
def set_document_tags(
    document_id: uuid.UUID,
    body: DocumentTagsPut,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    doc = _owned_doc(session, document_id, user.id)
    unique_ids = list(dict.fromkeys(body.tag_ids))
    if len(unique_ids) > 5:
        raise HTTPException(status_code=400, detail="一篇文档最多5个标签")
    for tag_id in unique_ids:
        tag = session.get(Tag, tag_id)
        if tag is None or tag.user_id != user.id:
            raise HTTPException(status_code=404, detail="标签不存在")
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))
    for tag_id in unique_ids:
        session.add(DocumentTag(document_id=document_id, tag_id=tag_id))
    session.commit()
    session.refresh(doc)
    return _document_out(doc, session, user.id)


@router.post("/{document_id}/favorite", response_model=DocumentOut)
def favorite_document(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    doc = _owned_doc(session, document_id, user.id)
    existing = session.get(Favorite, (user.id, document_id))
    if existing is None:
        session.add(Favorite(user_id=user.id, document_id=document_id))
        session.commit()
    session.refresh(doc)
    return _document_out(doc, session, user.id)


@router.delete("/{document_id}/favorite")
def unfavorite_document(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    _owned_doc(session, document_id, user.id)
    row = session.get(Favorite, (user.id, document_id))
    if row is not None:
        session.delete(row)
        session.commit()
    return {"ok": True}


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)):
    return _document_out(_owned_doc(session, document_id, user.id), session, user.id)


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkOut])
def list_document_chunks(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    doc = _owned_doc(session, document_id, user.id)
    return _chunks_for_document(doc, session)


@router.post("/{document_id}/chunks/{chunk_id}/reindex", response_model=DocumentChunkOut)
def reindex_document_chunk_http(
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = _owned_doc(session, document_id, user.id)
    chunk = session.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.document_id != doc.id:
        raise HTTPException(status_code=404, detail="切片不存在")
    try:
        ok = index_mod.reindex_chunk(chunk_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="切片不存在")
    updated = session.get(DocumentChunk, chunk_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="切片不存在")
    session.refresh(updated)
    return DocumentChunkOut(
        id=updated.id,
        chunk_index=updated.chunk_index,
        chunk_label=updated.chunk_label,
        content=updated.content,
        page=updated.page,
        heading=updated.heading,
        vector_status="ready",
        created_at=updated.created_at,
    )


@router.get("/{document_id}/related", response_model=list[RelatedDocumentOut])
def list_related_documents(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    doc = _owned_doc(session, document_id, user.id)
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    query = (doc.summary or "").strip() or doc.filename
    hits = search_chunks(session, query, user_id=user.id, knowledge_base_id=doc.knowledge_base_id, k=20)
    seen: set[uuid.UUID] = set()
    out: list[RelatedDocumentOut] = []
    for hit in hits:
        if hit.document_id == document_id or hit.document_id in seen:
            continue
        seen.add(hit.document_id)
        out.append(
            RelatedDocumentOut(
                document_id=hit.document_id,
                document_name=hit.document_name,
                score=hit.score,
                content=hit.content,
            )
        )
        if len(out) == 5:
            break
    return out


def _require_ready_llm(doc: Document | None) -> Document:
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail="文档未完成")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    return doc


@router.post("/{document_id}/summarize", response_model=DocumentOut)
def summarize(document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = _require_ready_llm(_owned_doc(session, document_id, user.id))
    text = gather_document_text(session, doc)
    if not text:
        raise HTTPException(status_code=400, detail="empty_content")
    doc.summary = summarize_document(text)
    session.commit()
    session.refresh(doc)
    return _document_out(doc, session, user.id)


@router.post("/{document_id}/auto-tags", response_model=DocumentOut)
def auto_tags(document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = _require_ready_llm(_owned_doc(session, document_id, user.id))
    text = gather_document_text(session, doc)
    if not text:
        raise HTTPException(status_code=400, detail="empty_content")
    existing_ids = set(
        session.scalars(select(DocumentTag.tag_id).where(DocumentTag.document_id == document_id))
    )
    for name in suggest_tag_names(text):
        tag = session.scalar(select(Tag).where(Tag.user_id == user.id, Tag.name == name))
        if tag is None:
            tag = Tag(user_id=user.id, name=name)
            session.add(tag)
            session.flush()
        if tag.id not in existing_ids:
            if len(existing_ids) >= 5:
                break
            session.add(DocumentTag(document_id=document_id, tag_id=tag.id))
            existing_ids.add(tag.id)
    session.commit()
    session.refresh(doc)
    return _document_out(doc, session, user.id)


def _upsert_entities(session: Session, knowledge_base_id: uuid.UUID, items: list[dict[str, str]]) -> None:
    for item in items:
        exists = session.scalar(
            select(Entity).where(
                Entity.knowledge_base_id == knowledge_base_id,
                Entity.name == item["name"],
                Entity.type == item["type"],
            )
        )
        if exists is None:
            session.add(Entity(knowledge_base_id=knowledge_base_id, name=item["name"], type=item["type"]))
    session.flush()


def _entity_by_name(session: Session, knowledge_base_id: uuid.UUID, name: str) -> Entity | None:
    return session.scalar(
        select(Entity).where(Entity.knowledge_base_id == knowledge_base_id, Entity.name == name).limit(1)
    )


@router.post("/{document_id}/graph", response_model=DocumentGraphOut)
def extract_document_graph(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    doc = _require_ready_llm(_owned_doc(session, document_id, user.id))
    text = gather_document_text(session, doc)
    if not text:
        raise HTTPException(status_code=400, detail="empty_content")
    entities, links = extract_graph(text)
    _upsert_entities(session, doc.knowledge_base_id, entities)
    session.execute(delete(EntityLink).where(EntityLink.document_id == doc.id))
    written: list[EntityLink] = []
    for item in links:
        src = _entity_by_name(session, doc.knowledge_base_id, item["from_name"])
        dst = _entity_by_name(session, doc.knowledge_base_id, item["to_name"])
        if src is None or dst is None or src.id == dst.id:
            continue
        row = EntityLink(from_id=src.id, to_id=dst.id, rel=item["rel"], document_id=doc.id)
        session.add(row)
        written.append(row)
    session.flush()
    saved_entities: list[Entity] = []
    for item in entities:
        row = session.scalar(
            select(Entity).where(
                Entity.knowledge_base_id == doc.knowledge_base_id,
                Entity.name == item["name"],
                Entity.type == item["type"],
            )
        )
        if row is not None:
            saved_entities.append(row)
    out = DocumentGraphOut(
        document_id=doc.id,
        entities=[GraphEntityOut(id=row.id, name=row.name, type=row.type) for row in saved_entities],
        links=[
            GraphLinkOut(from_id=row.from_id, to_id=row.to_id, rel=row.rel, document_id=row.document_id)
            for row in written
        ],
    )
    session.commit()
    return out


@router.get("/{document_id}/parsed.md")
def get_parsed_markdown(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    _owned_doc(session, document_id, user.id)
    path = parsed_dir(document_id) / "document.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="解析稿不存在")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.delete("/{document_id}")
def delete_document(document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = _owned_doc(session, document_id, user.id)
    remove_document_files(doc)
    try:
        delete_document_chunks(document_id)
    except EsNotConfiguredError:
        pass
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    session.execute(delete(Favorite).where(Favorite.document_id == document_id))
    session.delete(doc)
    session.commit()
    return {"ok": True}


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex_document_http(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    _owned_doc(session, document_id, user.id)
    try:
        index_mod.reindex_document(document_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"重新处理失败：{exc}") from exc
    doc = _owned_doc(session, document_id, user.id)
    return _document_out(doc, session, user.id)


@router.post("/{document_id}/index", response_model=DocumentOut)
def index_document_http(
    document_id: uuid.UUID, session: Session = Depends(get_db), user: User = Depends(current_user)
):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = _owned_doc(session, document_id, user.id)
    index_mod.index_document(document_id)
    session.refresh(doc)
    return _document_out(doc, session, user.id)

