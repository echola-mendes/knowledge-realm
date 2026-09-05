from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

# (max_age_hours exclusive upper bound, freshness fraction). Last tier ends at 24h.
FRESHNESS_TIERS: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),
    (3.0, 0.9),
    (6.0, 0.75),
    (12.0, 0.55),
    (24.0, 0.3),
)

IMPORTANCE_WEIGHT = 0.45
SOURCE_WEIGHT = 0.25
FRESHNESS_WEIGHT = 0.30


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def now_shanghai(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(SHANGHAI)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc).astimezone(SHANGHAI)
    return now.astimezone(SHANGHAI)


def shanghai_today(now: datetime | None = None) -> date:
    return now_shanghai(now).date()


def event_time(
    published_at: datetime | None,
    collected_at: datetime,
) -> datetime:
    """RSS 无 published_at 时用 collected_at。返回带时区的 UTC 或原时区。"""
    raw = published_at if published_at is not None else collected_at
    if raw.tzinfo is None:
        return raw.replace(tzinfo=timezone.utc)
    return raw


def age_hours(event_at: datetime, now: datetime | None = None) -> float:
    current = now_shanghai(now)
    evt = event_at if event_at.tzinfo is not None else event_at.replace(tzinfo=timezone.utc)
    delta = current - evt.astimezone(SHANGHAI)
    return delta.total_seconds() / 3600.0


def freshness_fraction(event_at: datetime, now: datetime | None = None) -> float | None:
    """返回 0～1 的新鲜度系数；超过 24h 返回 None（不入当日热榜）。"""
    hours = age_hours(event_at, now)
    if hours < 0:
        return 1.0
    for upper, fraction in FRESHNESS_TIERS:
        if hours < upper:
            return fraction
    return None


def compute_heat_score(
    importance_score: int,
    source_weight: float,
    freshness: float,
) -> float:
    """
    importance_norm = (importance - 1) / 9 * 100
    source_norm = source_weight (0～100)
    freshness_norm = freshness_fraction * 100
    """
    importance = max(1, min(10, int(importance_score)))
    importance_norm = (importance - 1) / 9 * 100.0
    source_norm = float(source_weight)
    freshness_norm = float(freshness) * 100.0
    raw = (
        IMPORTANCE_WEIGHT * importance_norm
        + SOURCE_WEIGHT * source_norm
        + FRESHNESS_WEIGHT * freshness_norm
    )
    return clamp(raw)


def is_eligible_for_daily_rank(
    event_at: datetime,
    *,
    rank_date: date | None = None,
    now: datetime | None = None,
) -> bool:
    """发布时间落在榜单日（上海），且相对现在未超过 24 小时。"""
    current = now_shanghai(now)
    day = rank_date if rank_date is not None else current.date()
    evt_local = (
        event_at if event_at.tzinfo is not None else event_at.replace(tzinfo=timezone.utc)
    ).astimezone(SHANGHAI)
    if evt_local.date() != day:
        return False
    return freshness_fraction(event_at, current) is not None


@dataclass(frozen=True)
class RankCandidate:
    news_id: int
    category: str
    heat_score: float


def select_top_k(candidates: list[RankCandidate], k: int) -> list[RankCandidate]:
    """按 heat 降序取 TopK；不足 k 条不强行补齐。"""
    if k <= 0:
        return []
    ordered = sorted(candidates, key=lambda c: (-c.heat_score, c.news_id))
    return ordered[:k]


def build_category_ranks(
    candidates: list[RankCandidate],
    categories: list[str],
    *,
    top_k: int,
) -> dict[str, list[RankCandidate]]:
    """各分类独立 TopK，不跨分类补榜。"""
    by_cat: dict[str, list[RankCandidate]] = {c: [] for c in categories}
    for item in candidates:
        if item.category in by_cat:
            by_cat[item.category].append(item)
    return {cat: select_top_k(items, top_k) for cat, items in by_cat.items()}


def build_all_rank(candidates: list[RankCandidate], *, top_k: int) -> list[RankCandidate]:
    """综合榜：合并后按 heat 取 TopK（非三榜拼接）。"""
    return select_top_k(candidates, top_k)
