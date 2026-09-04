from __future__ import annotations

from app.news_service import NewsService


def handle_news_refresh(_payload: dict) -> dict:
    return NewsService().refresh()
