from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import News
from app.news.parser import NewsItem

DedupAction = Literal["insert", "update", "skip"]


@dataclass(frozen=True)
class DedupResult:
    action: DedupAction
    news: News | None = None
    reason: str | None = None

    @property
    def needs_llm(self) -> bool:
        return self.action == "insert"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def apply_dedup(session: Session, item: NewsItem) -> DedupResult:
    """URL unique → update time fields, no LLM; title hash conflict → skip; else insert candidate."""
    by_url = session.scalar(select(News).where(News.url == item.url))
    if by_url is not None:
        by_url.collected_at = _utcnow()
        if item.published_at is not None:
            by_url.published_at = item.published_at
        if item.content is not None:
            by_url.content = item.content
        by_url.updated_at = _utcnow()
        session.flush()
        return DedupResult(action="update", news=by_url, reason="url_exists")

    by_hash = session.scalar(select(News).where(News.content_hash == item.content_hash))
    if by_hash is not None:
        return DedupResult(action="skip", news=by_hash, reason="title_hash_exists")

    row = News(
        title=item.title,
        summary=None,
        content=item.content,
        url=item.url,
        source=item.source,
        category=item.category,
        published_at=item.published_at,
        collected_at=_utcnow(),
        importance_score=None,
        heat_score=None,
        content_hash=item.content_hash,
    )
    session.add(row)
    session.flush()
    return DedupResult(action="insert", news=row, reason=None)
