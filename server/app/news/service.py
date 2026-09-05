from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import News, NewsDailyRank
from app.news.collector import collect_sources
from app.news.dedup import apply_dedup
from app.news.parser import NewsItem, parse_feed
from app.news.scorer import (
    RankCandidate,
    build_all_rank,
    build_category_ranks,
    compute_heat_score,
    event_time,
    freshness_fraction,
    is_eligible_for_daily_rank,
    shanghai_today,
)
from app.news.sources import ALLOWED_CATEGORIES, load_sources
from app.news.summarizer import summarize_item


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_categories(categories: Iterable[str] | None) -> list[str]:
    if categories is None:
        return sorted(ALLOWED_CATEGORIES)
    cleaned = sorted({c.strip().lower() for c in categories if c and str(c).strip()})
    unknown = set(cleaned) - ALLOWED_CATEGORIES
    if unknown:
        raise ValueError(f"invalid categories: {sorted(unknown)}")
    return cleaned


def _item_sort_key(item: NewsItem) -> tuple:
    pub = item.published_at
    if pub is None:
        return (1, 0)
    ts = pub if pub.tzinfo is not None else pub.replace(tzinfo=timezone.utc)
    return (0, -ts.timestamp())


def _truncate_fair(
    items: list[NewsItem],
    max_items: int,
    categories: list[str],
) -> list[NewsItem]:
    """按分类均分名额后再合并，避免单一大源（如 BBC）占满 NEWS_MAX_ITEMS。"""
    if max_items <= 0:
        return []
    if len(items) <= max_items:
        return items
    cats = list(categories) or sorted({i.category for i in items})
    if not cats:
        return items[:max_items]
    by_cat: dict[str, list[NewsItem]] = {c: [] for c in cats}
    for item in items:
        bucket = by_cat.get(item.category)
        if bucket is not None:
            bucket.append(item)
    n = len(cats)
    base, rem = divmod(max_items, n)
    chosen: list[NewsItem] = []
    leftovers: list[NewsItem] = []
    for i, cat in enumerate(cats):
        quota = base + (1 if i < rem else 0)
        bucket = by_cat[cat]
        chosen.extend(bucket[:quota])
        leftovers.extend(bucket[quota:])
    if len(chosen) < max_items:
        leftovers.sort(key=_item_sort_key)
        need = max_items - len(chosen)
        chosen.extend(leftovers[:need])
    chosen.sort(key=_item_sort_key)
    return chosen[:max_items]


def _source_weight_map() -> dict[str, float]:
    mapping: dict[str, float] = {}
    for source in load_sources(enabled_only=False):
        mapping[source.name] = source.weight
    return mapping


def _score_news(news: News, source_weight: float, *, now: datetime | None = None) -> float | None:
    evt = event_time(news.published_at, news.collected_at)
    frac = freshness_fraction(evt, now)
    if frac is None:
        return None
    importance = news.importance_score if news.importance_score is not None else 5
    return compute_heat_score(importance, source_weight, frac)


def rewrite_daily_ranks(
    session: Session,
    categories: list[str],
    *,
    top_k: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """重写当日相关 category + all 的 rank 快照。不足 top_k 不跨分类补榜。"""
    settings = get_settings()
    k = int(top_k if top_k is not None else settings.news_top_k)
    rank_date = shanghai_today(now)
    weights = _source_weight_map()

    rows = list(session.scalars(select(News).where(News.category.in_(categories))).all())
    candidates: list[RankCandidate] = []
    for news in rows:
        weight = weights.get(news.source, 50.0)
        heat = _score_news(news, weight, now=now)
        if heat is None:
            continue
        evt = event_time(news.published_at, news.collected_at)
        if not is_eligible_for_daily_rank(evt, rank_date=rank_date, now=now):
            continue
        news.heat_score = heat
        news.updated_at = _utcnow()
        candidates.append(
            RankCandidate(news_id=news.id, category=news.category, heat_score=heat)
        )

    by_cat = build_category_ranks(candidates, categories, top_k=k)
    all_board = build_all_rank(candidates, top_k=k)

    cats_to_clear = list(categories) + ["all"]
    session.execute(
        delete(NewsDailyRank).where(
            NewsDailyRank.rank_date == rank_date,
            NewsDailyRank.category.in_(cats_to_clear),
        )
    )

    written = 0
    for cat, items in by_cat.items():
        for idx, item in enumerate(items, start=1):
            session.add(
                NewsDailyRank(
                    news_id=item.news_id,
                    rank_date=rank_date,
                    category=cat,
                    rank=idx,
                    score=item.heat_score,
                )
            )
            written += 1
    for idx, item in enumerate(all_board, start=1):
        session.add(
            NewsDailyRank(
                news_id=item.news_id,
                rank_date=rank_date,
                category="all",
                rank=idx,
                score=item.heat_score,
            )
        )
        written += 1

    session.flush()
    return {"rank_rows": written, "candidates": len(candidates)}


def refresh(
    session: Session,
    categories: Iterable[str] | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """采集 → 解析 → 去重 → 摘要/重要性 → 热度 → 写当日排行榜。不 commit（由调用方负责）。"""
    cats = _normalize_categories(categories)
    settings = get_settings()
    max_items = settings.news_max_items

    sources = load_sources(categories=cats, enabled_only=True)
    collect_results = collect_sources(sources)

    items: list[NewsItem] = []
    source_errors: list[str] = []
    for result in collect_results:
        if not result.ok or result.body is None:
            source_errors.append(f"{result.source.id}:{result.error or 'empty_body'}")
            continue
        items.extend(parse_feed(result.body, result.source))

    items.sort(key=_item_sort_key)
    truncated = _truncate_fair(items, max_items, cats)

    fetched = len(items)
    saved = 0
    summarized = 0
    failed = 0
    skipped_dup = 0

    for item in truncated:
        try:
            with session.begin_nested():
                dedup = apply_dedup(session, item)
                if dedup.action == "skip":
                    skipped_dup += 1
                    continue
                if dedup.action == "update":
                    news = dedup.news
                    assert news is not None
                    evt = event_time(news.published_at, news.collected_at)
                    # Only spend LLM on items that can enter today's board.
                    if news.summary is None and is_eligible_for_daily_rank(evt, now=now):
                        result = summarize_item(
                            title=news.title,
                            content=news.content,
                            category=news.category,
                        )
                        if result.ok and result.summary is not None:
                            summarized += 1
                        elif not result.ok:
                            failed += 1
                        news.summary = result.summary
                        news.importance_score = result.importance
                    heat = _score_news(news, item.weight, now=now)
                    if heat is not None:
                        news.heat_score = heat
                    continue

                news = dedup.news
                assert news is not None
                saved += 1
                evt = event_time(news.published_at, news.collected_at)
                if is_eligible_for_daily_rank(evt, now=now):
                    result = summarize_item(
                        title=news.title,
                        content=news.content,
                        category=news.category,
                    )
                    if result.ok and result.summary is not None:
                        summarized += 1
                    elif not result.ok:
                        failed += 1
                    news.summary = result.summary
                    news.importance_score = result.importance
                else:
                    news.importance_score = 5
                heat = _score_news(news, item.weight, now=now)
                if heat is not None:
                    news.heat_score = heat
                news.updated_at = _utcnow()
        except Exception:  # noqa: BLE001 — per-item isolation
            failed += 1

    rank_meta = rewrite_daily_ranks(session, cats, now=now)
    return {
        "categories": cats,
        "fetched": fetched,
        "saved": saved,
        "summarized": summarized,
        "failed": failed,
        "skipped_dup": skipped_dup,
        "source_errors": source_errors,
        **rank_meta,
    }
