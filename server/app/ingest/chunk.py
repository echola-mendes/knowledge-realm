from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
CHUNK_SIZE = DEFAULT_CHUNK_SIZE
CHUNK_OVERLAP = DEFAULT_CHUNK_OVERLAP
PAGE_RE = re.compile(r"Page\s+(\d+)", re.IGNORECASE)
TABLE_RE = re.compile(r"(?:^\|[^\n]+\|(?:\n|$))+", re.MULTILINE)
FAQ_Q_RE = re.compile(r"[?？]\s*$")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
SHORT_CHUNK_CHARS = 50
SENTENCE_END_RE = re.compile(r"[。！？.!?”』」）)\]]\s*$")
TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|\s*$", re.MULTILINE)


def quality_labels(content: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    """Chunk 质量标签：正常 / 过短切片 / 超长切片 / 疑似断句 / 残缺表格。"""
    text = content.strip()
    if not text:
        return ["过短切片"]
    labels: list[str] = []
    length = len(text)
    if length < SHORT_CHUNK_CHARS:
        labels.append("过短切片")
    if length > chunk_size * 1.5:
        labels.append("超长切片")
    lines = [ln for ln in text.split("\n") if ln.lstrip().startswith("|")]
    if lines and not TABLE_SEP_RE.search(text):
        labels.append("残缺表格")
    if length >= SHORT_CHUNK_CHARS and not SENTENCE_END_RE.search(text) and not lines:
        labels.append("疑似断句")
    return labels or ["正常"]


def chunk_meta(content: str, heading: str | None, page: int | None) -> dict:
    """切片元数据：标题层级 / 页码 / 特殊处理标记（表格保护、FAQ 合并）。"""
    meta: dict = {"heading": heading, "page": page, "level": None, "table": False, "faq": False}
    match = HEADING_RE.search(content)
    if match:
        meta["level"] = len(match.group(1))
        meta["heading"] = match.group(2).strip()
    elif heading:
        meta["heading"] = heading
    if TABLE_RE.search(content):
        meta["table"] = True
    non_empty = [ln for ln in content.split("\n") if ln.strip()]
    if len(non_empty) >= 2 and FAQ_Q_RE.search(non_empty[0]) and not non_empty[1].lstrip().startswith("#"):
        meta["faq"] = True
    return meta


@dataclass
class TextChunk:
    content: str
    page: int | None
    heading: str | None


def _protect_tables(text: str) -> tuple[str, dict[str, str]]:
    tables: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        key = f"[[TBL{len(tables)}]]"
        tables[key] = match.group(0).rstrip("\n")
        return key

    return TABLE_RE.sub(repl, text), tables


def _restore_tables(text: str, tables: dict[str, str]) -> str:
    for key, table in tables.items():
        text = text.replace(key, table)
    return text


def _bind_faq(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if FAQ_Q_RE.search(line) and i + 1 < len(lines):
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and not lines[j].lstrip().startswith("#"):
                out.append(line + "\n" + lines[j])
                i = j + 1
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _heading_from_meta(meta: dict) -> str | None:
    for key in ("h1", "h2", "h3"):
        value = meta.get(key)
        if value:
            return str(value)
    return None


def _page_of(heading: str | None, content: str) -> int | None:
    for source in (heading or "", content):
        match = PAGE_RE.search(source)
        if match:
            return int(match.group(1))
    return None


def split_markdown(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    if not text.strip():
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be < chunk_size")
    prepared = _bind_faq(text)
    prepared, tables = _protect_tables(prepared)
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    sections = header_splitter.split_text(prepared)
    if not sections:
        return []
    rec = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[TextChunk] = []
    for section in sections:
        heading = _heading_from_meta(section.metadata)
        body = section.page_content
        if any(token in body for token in tables) and len(_restore_tables(body, tables)) > chunk_size:
            restored = _restore_tables(body, tables).strip()
            if restored:
                chunks.append(TextChunk(restored, _page_of(heading, restored), heading))
            continue
        pieces = rec.split_text(body) if len(body) > chunk_size else [body]
        for piece in pieces:
            restored = _restore_tables(piece, tables).strip()
            if not restored:
                continue
            chunks.append(TextChunk(restored, _page_of(heading, restored), heading))
    return chunks
