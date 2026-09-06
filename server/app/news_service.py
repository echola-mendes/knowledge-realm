from __future__ import annotations

from typing import Iterable

from app.db import session_scope
from app.news.service import PipelineProgress
from app.news.service import refresh as refresh_pipeline


class NewsService:
    """Thin facade for worker / callers; pipeline lives in app.news.service."""

    def refresh(
        self,
        categories: Iterable[str] | None = None,
        *,
        progress: PipelineProgress | None = None,
    ) -> dict:
        session = session_scope()
        try:
            result = refresh_pipeline(session, categories, progress=progress)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
