from __future__ import annotations

from app.worker.handlers.news_handler import handle_news_refresh

HANDLERS = {
    "NEWS_REFRESH": handle_news_refresh,
}
