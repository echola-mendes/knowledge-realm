from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import struct_time
from typing import Any

import feedparser

from app.news.sources import NewsSource

_WS_RE = re.compile(r"\s+")
# Keep letters/digits/CJK/spaces; drop punctuation and other symbols ("无意义符号").
_SYMBOL_RE = re.compile(r"[^\w\u4e00-\u9fff\s]+", flags=re.UNICODE)


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    content: str | None
    published_at: datetime | None
    source: str
    category: str
    weight: float
    content_hash: str


def normalize_title(title: str) -> str:
    text = title.strip().lower()
    text = _WS_RE.sub(" ", text)
    text = _SYMBOL_RE.sub("", text)
    return _WS_RE.sub(" ", text).strip()


def title_content_hash(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()


def _entry_url(entry: Any) -> str | None:
    link = getattr(entry, "link", None) or entry.get("link") if isinstance(entry, dict) else None
    if isinstance(link, str) and link.strip():
        return link.strip()
    links = getattr(entry, "links", None) or (entry.get("links") if isinstance(entry, dict) else None)
    if isinstance(links, list):
        for item in links:
            href = item.get("href") if isinstance(item, dict) else getattr(item, "href", None)
            if isinstance(href, str) and href.strip():
                return href.strip()
    return None


def _entry_content(entry: Any) -> str | None:
    content = getattr(entry, "content", None)
    if isinstance(content, list) and content:
        value = content[0].get("value") if isinstance(content[0], dict) else getattr(content[0], "value", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("summary", "description"):
        value = getattr(entry, key, None) or (entry.get(key) if isinstance(entry, dict) else None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _struct_time_to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=timezone.utc)


def _entry_published_at(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, key, None)
        dt = _struct_time_to_datetime(parsed)
        if dt is not None:
            return dt
    for key in ("published", "updated"):
        raw = getattr(entry, key, None) or (entry.get(key) if isinstance(entry, dict) else None)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            dt = parsedate_to_datetime(raw.strip())
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def parse_feed(body: str, source: NewsSource) -> list[NewsItem]:
    """Parse RSS/Atom body into unified NewsItem list. Content may be None; never fetches pages."""
    parsed = feedparser.parse(body)
    items: list[NewsItem] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", None) or ""
        if not isinstance(title, str):
            title = str(title)
        title = title.strip()
        url = _entry_url(entry)
        if not title or not url:
            continue
        items.append(
            NewsItem(
                title=title,
                url=url,
                content=_entry_content(entry),
                published_at=_entry_published_at(entry),
                source=source.name,
                category=source.category,
                weight=source.weight,
                content_hash=title_content_hash(title),
            )
        )
    return items
