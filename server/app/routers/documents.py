from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.kb import resolve_knowledge_base_id
from app.llm import llm_keys_ready
from app.models import Document, DocumentChunk, DocumentTag, Favorite, KnowledgeBase, Tag
from app.p1.chains import gather_document_text, suggest_tag_names, summarize_document
from app.schemas import DocumentOut, DocumentTagsPut, NoteCreate, UrlCreate
from app import index as index_mod
from app.storage import original_path, parsed_dir, remove_document_files, write_original

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED = {".pdf": "pdf", ".docx": "docx", ".md": "md", ".markdown": "md", ".txt": "txt"}
UPLOAD_MAX_BYTES = 100 * 1024 * 1024
STATUS_PENDING = "pending"


def get_db():
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def _normalize_ext(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _document_out(doc: Document, session: Session, *, existed: bool = False) -> DocumentOut:
    tag_ids = list(session.scalars(select(DocumentTag.tag_id).where(DocumentTag.document_id == doc.id)))
    fav = session.get(Favorite, doc.id) is not None
    return DocumentOut.model_validate(doc).model_copy(
        update={
            "existed": existed,
            "source_url": doc.source_url,
            "source_path": str(original_path(doc.id, doc.ext)),
            "tag_ids": tag_ids,
            "is_favorite": fav,
        }
    )


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: uuid.UUID | None = Form(None),
    session: Session = Depends(get_db),
):
    ext = _normalize_ext(file.filename or "")
    if ext not in ALLOWED:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    data = await file.read()
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 100MB")
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id)
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    checksum = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, session, existed=True)
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
    return _document_out(doc, session, existed=False)


@router.post("/notes", response_model=DocumentOut)
def create_note(
    body: NoteCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
):
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="笔记内容为空")
    kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id)
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    data = text.encode("utf-8")
    checksum = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, session, existed=True)
    doc_id = uuid.uuid4()
    write_original(doc_id, ".md", data)
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=body.filename or "笔记.md",
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
    return _document_out(doc, session, existed=False)


@router.post("/url", response_model=DocumentOut)
def create_url_document(
    body: UrlCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="只支持 http/https 公开页")
    kb_id = resolve_knowledge_base_id(session, body.knowledge_base_id)
    if session.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    checksum = hashlib.sha256(url.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.knowledge_base_id == kb_id, Document.checksum == checksum)
    )
    if existing is not None:
        return _document_out(existing, session, existed=True)
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
    return _document_out(doc, session, existed=False)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    knowledge_base_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    favorite: bool | None = None,
    session: Session = Depends(get_db),
):
    kb_id = resolve_knowledge_base_id(session, knowledge_base_id)
    stmt = select(Document).where(Document.knowledge_base_id == kb_id)
    if tag_id is not None:
        stmt = stmt.join(DocumentTag).where(DocumentTag.tag_id == tag_id)
    if favorite is True:
        stmt = stmt.join(Favorite, Favorite.document_id == Document.id)
    rows = session.scalars(stmt.order_by(Document.created_at.desc())).all()
    return [_document_out(row, session) for row in rows]


@router.put("/{document_id}/tags", response_model=DocumentOut)
def set_document_tags(
    document_id: uuid.UUID,
    body: DocumentTagsPut,
    session: Session = Depends(get_db),
):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    unique_ids = list(dict.fromkeys(body.tag_ids))
    for tag_id in unique_ids:
        if session.get(Tag, tag_id) is None:
            raise HTTPException(status_code=404, detail="标签不存在")
    session.execute(delete(DocumentTag).where(DocumentTag.document_id == document_id))
    for tag_id in unique_ids:
        session.add(DocumentTag(document_id=document_id, tag_id=tag_id))
    session.commit()
    session.refresh(doc)
    return _document_out(doc, session)


@router.post("/{document_id}/favorite", response_model=DocumentOut)
def favorite_document(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    existing = session.get(Favorite, document_id)
    if existing is None:
        session.add(Favorite(document_id=document_id))
        session.commit()
    session.refresh(doc)
    return _document_out(doc, session)


@router.delete("/{document_id}/favorite")
def unfavorite_document(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    row = session.get(Favorite, document_id)
    if row is not None:
        session.delete(row)
        session.commit()
    return {"ok": True}


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _document_out(doc, session)


def _require_ready_llm(doc: Document | None) -> Document:
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail="文档未完成")
    if not llm_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    return doc


@router.post("/{document_id}/summarize", response_model=DocumentOut)
def summarize(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = _require_ready_llm(session.get(Document, document_id))
    text = gather_document_text(session, doc)
    if not text:
        raise HTTPException(status_code=400, detail="empty_content")
    doc.summary = summarize_document(text)
    session.commit()
    session.refresh(doc)
    return _document_out(doc, session)


@router.post("/{document_id}/auto-tags", response_model=DocumentOut)
def auto_tags(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = _require_ready_llm(session.get(Document, document_id))
    text = gather_document_text(session, doc)
    if not text:
        raise HTTPException(status_code=400, detail="empty_content")
    existing_ids = set(
        session.scalars(select(DocumentTag.tag_id).where(DocumentTag.document_id == document_id))
    )
    for name in suggest_tag_names(text):
        tag = session.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()
        if tag.id not in existing_ids:
            session.add(DocumentTag(document_id=document_id, tag_id=tag.id))
            existing_ids.add(tag.id)
    session.commit()
    session.refresh(doc)
    return _document_out(doc, session)


@router.get("/{document_id}/parsed.md")
def get_parsed_markdown(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    path = parsed_dir(document_id) / "document.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="解析稿不存在")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.delete("/{document_id}")
def delete_document(document_id: uuid.UUID, session: Session = Depends(get_db)):
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    remove_document_files(doc)
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    session.execute(delete(Favorite).where(Favorite.document_id == document_id))
    session.delete(doc)
    session.commit()
    return {"ok": True}


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex_document_http(document_id: uuid.UUID, session: Session = Depends(get_db)):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    index_mod.reindex_document(document_id)
    session.refresh(doc)
    return _document_out(doc, session)


@router.post("/{document_id}/index", response_model=DocumentOut)
def index_document_http(document_id: uuid.UUID, session: Session = Depends(get_db)):
    if not index_mod.embedding_keys_ready():
        raise HTTPException(status_code=503, detail="未配置 Embedding API Key")
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    index_mod.index_document(document_id)
    session.refresh(doc)
    return _document_out(doc, session)
