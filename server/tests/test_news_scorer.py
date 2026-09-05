from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.news.scorer import (
    RankCandidate,
    build_all_rank,
    build_category_ranks,
    compute_heat_score,
    freshness_fraction,
    select_top_k,
)


def test_heat_score_in_expected_range_for_tiers():
    # importance=10 → norm 100; weight 80; freshness 1h → 100%
    # 0.45*100 + 0.25*80 + 0.30*100 = 45 + 20 + 30 = 95
    assert compute_heat_score(10, 80.0, 1.0) == 95.0

    # importance=5 → norm (5-1)/9*100 = 44.444...; weight 100; freshness 30%
    # 0.45*44.444... + 0.25*100 + 0.30*30 ≈ 20 + 25 + 9 = 54
    heat = compute_heat_score(5, 100.0, 0.3)
    assert 53.0 <= heat <= 55.0

    # importance fail mid-tier 5, low weight, mid freshness
    heat2 = compute_heat_score(5, 40.0, 0.75)
    assert 0.0 <= heat2 <= 100.0
    # 0.45*44.444 + 0.25*40 + 0.30*75 ≈ 20 + 10 + 22.5 = 52.5
    assert 51.0 <= heat2 <= 54.0


def test_freshness_tiers_match_prd():
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)

    def at_hours(h: float) -> datetime:
        return now - timedelta(hours=h)

    assert freshness_fraction(at_hours(0.5), now) == 1.0
    assert freshness_fraction(at_hours(2.0), now) == 0.9
    assert freshness_fraction(at_hours(4.0), now) == 0.75
    assert freshness_fraction(at_hours(8.0), now) == 0.55
    assert freshness_fraction(at_hours(18.0), now) == 0.3
    assert freshness_fraction(at_hours(25.0), now) is None


def test_category_rank_does_not_cross_fill_when_under_top_k():
    candidates = [
        RankCandidate(news_id=1, category="technology", heat_score=90),
        RankCandidate(news_id=2, category="technology", heat_score=80),
        RankCandidate(news_id=3, category="ai", heat_score=95),
        RankCandidate(news_id=4, category="finance", heat_score=70),
        RankCandidate(news_id=5, category="finance", heat_score=60),
    ]
    # finance only has 2; top_k=5 must NOT pull from technology/ai
    ranks = build_category_ranks(
        candidates,
        ["technology", "ai", "finance"],
        top_k=5,
    )
    assert len(ranks["technology"]) == 2
    assert len(ranks["ai"]) == 1
    assert len(ranks["finance"]) == 2
    assert {c.news_id for c in ranks["finance"]} == {4, 5}
    assert all(c.category == "finance" for c in ranks["finance"])


def test_all_rank_is_merge_then_topk_not_concat():
    # If we concatenated each category's top1 we'd get ids 1,3,10 (heats 90,88,50)
    # Merge-then-topk should prefer high heat across categories: 1,2,3 (90,89,88)
    candidates = [
        RankCandidate(news_id=1, category="technology", heat_score=90),
        RankCandidate(news_id=2, category="technology", heat_score=89),
        RankCandidate(news_id=3, category="ai", heat_score=88),
        RankCandidate(news_id=10, category="finance", heat_score=50),
    ]
    cat_top1 = []
    for cat in ("technology", "ai", "finance"):
        cat_top1.extend(select_top_k([c for c in candidates if c.category == cat], 1))
    concat_ids = [c.news_id for c in cat_top1]

    merged = build_all_rank(candidates, top_k=3)
    merged_ids = [c.news_id for c in merged]

    assert concat_ids == [1, 3, 10]
    assert merged_ids == [1, 2, 3]
    assert merged_ids != concat_ids
