from __future__ import annotations

from sqlalchemy import select

from app.db import session_scope
from app.models import NewsSettings
from app.news_service import NewsService


def _enabled_categories() -> list[str]:
    session = session_scope()
    try:
        row = session.scalar(select(NewsSettings).order_by(NewsSettings.id.asc()).limit(1))
        if row is None:
            raise RuntimeError("news_settings missing; run migrations")
        cats = [
            c.strip().lower()
            for c in (row.enabled_categories or [])
            if isinstance(c, str) and c.strip()
        ]
        if not cats:
            raise RuntimeError("news_settings.enabled_categories is empty")
        return cats
    finally:
        session.close()


def handle_news_refresh(_payload: dict) -> dict:
    categories = _enabled_categories()
    return NewsService().refresh(categories)
