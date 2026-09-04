from __future__ import annotations


class NewsService:
    def refresh(self) -> dict:
        return {"news_pipeline_pending": True}
