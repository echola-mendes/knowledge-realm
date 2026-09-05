from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import current_user, get_db
from app.models import News, NewsDailyRank, NewsSettings, User
from app.news.scorer import shanghai_today
from app.news.sources import ALLOWED_CATEGORIES
from app.schemas import (
    NewsDetailOut,
    NewsHotItemOut,
    NewsHotOut,
    NewsSettingsIn,
    NewsSettingsOut,
)

router = APIRouter(prefix="/api/news", tags=["news"])

HOT_CATEGORIES = frozenset({"all"}) | ALLOWED_CATEGORIES


def _normalize_setting_categories(raw: list[str]) -> list[str]:
    cleaned = sorted(
        {
            c.strip().lower()
            for c in raw
            if isinstance(c, str) and c.strip()
        }
    )
    if not cleaned:
        raise HTTPException(status_code=400, detail="至少启用一个分类")
    unknown = set(cleaned) - ALLOWED_CATEGORIES
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"invalid categories: {sorted(unknown)}",
        )
    return cleaned


def _get_settings_row(session: Session) -> NewsSettings:
    row = session.scalar(select(NewsSettings).order_by(NewsSettings.id.asc()).limit(1))
    if row is None:
        raise HTTPException(status_code=500, detail="news_settings missing")
    return row


@router.get("/hot", response_model=NewsHotOut)
def get_hot(
    category: str = Query(default="all"),
    date_param: date | None = Query(default=None, alias="date"),
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    cat = category.strip().lower() if category else "all"
    if cat not in HOT_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"invalid category: {category}")
    rank_date = date_param or shanghai_today()
    top_k = get_settings().news_top_k
    rows = session.execute(
        select(NewsDailyRank, News)
        .join(News, News.id == NewsDailyRank.news_id)
        .where(
            NewsDailyRank.rank_date == rank_date,
            NewsDailyRank.category == cat,
        )
        .order_by(NewsDailyRank.rank.asc())
        .limit(top_k)
    ).all()
    items = [
        NewsHotItemOut(
            id=news.id,
            rank=rank.rank,
            title=news.title,
            summary=news.summary,
            category=news.category,
            source=news.source,
            published_at=news.published_at,
            heat_score=news.heat_score if news.heat_score is not None else rank.score,
        )
        for rank, news in rows
    ]
    return NewsHotOut(date=rank_date, category=cat, items=items)


@router.get("/settings", response_model=NewsSettingsOut)
def get_settings_api(
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    row = _get_settings_row(session)
    return NewsSettingsOut(enabled_categories=list(row.enabled_categories or []))


@router.put("/settings", response_model=NewsSettingsOut)
def put_settings(
    body: NewsSettingsIn,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    cats = _normalize_setting_categories(body.enabled_categories)
    row = _get_settings_row(session)
    row.enabled_categories = cats
    session.commit()
    session.refresh(row)
    return NewsSettingsOut(enabled_categories=list(row.enabled_categories or []))


@router.get("/{news_id}", response_model=NewsDetailOut)
def get_news_detail(
    news_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(current_user),
):
    news = session.get(News, news_id)
    if news is None:
        raise HTTPException(status_code=404, detail="资讯不存在")
    return news
