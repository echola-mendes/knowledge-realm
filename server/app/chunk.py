from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
PAGE_RE = re.compile(r"Page\s+(\d+)", re.IGNORECASE)
TABLE_RE = re.compile(r"(?:^\|[^\n]+\|(?:\n|$))+", re.MULTILINE)
FAQ_Q_RE = re.compile(r"[?？]\s*$")


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


def split_markdown(text: str) -> list[TextChunk]:
    if not text.strip():
        return []
    prepared = _bind_faq(text)
    prepared, tables = _protect_tables(prepared)
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
        strip_headers=False,
    )
    sections = header_splitter.split_text(prepared)
    if not sections:
        return []
    rec = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks: list[TextChunk] = []
    for section in sections:
        heading = _heading_from_meta(section.metadata)
        body = section.page_content
        if any(token in body for token in tables) and len(_restore_tables(body, tables)) > CHUNK_SIZE:
            restored = _restore_tables(body, tables).strip()
            if restored:
                chunks.append(TextChunk(restored, _page_of(heading, restored), heading))
            continue
        pieces = rec.split_text(body) if len(body) > CHUNK_SIZE else [body]
        for piece in pieces:
            restored = _restore_tables(piece, tables).strip()
            if not restored:
                continue
            chunks.append(TextChunk(restored, _page_of(heading, restored), heading))
    return chunks
