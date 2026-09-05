from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.db import session_scope
from app.models import News
from app.news.dedup import apply_dedup
from app.news.parser import NewsItem, normalize_title, parse_feed, title_content_hash
from app.news.sources import NewsSource

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "news_sample.rss"


def _source(**overrides) -> NewsSource:
    base = dict(
        id="fixture",
        name="Fixture Source",
        url="https://example.com/feed",
        type="rss",
        category="ai",
        weight=80.0,
        enabled=True,
    )
    base.update(overrides)
    return NewsSource(**base)


def test_normalize_title_and_hash_stable():
    assert normalize_title("  OpenAI   Releases   GPT Update!!! ") == "openai releases gpt update"
    assert title_content_hash("OpenAI Releases GPT Update") == title_content_hash(
        "  openai   releases   gpt update!!! "
    )


def test_parse_feed_fixture_stable_fields():
    body = _FIXTURE.read_text(encoding="utf-8")
    items = parse_feed(body, _source())
    assert len(items) == 2

    first = items[0]
    assert first.title == "OpenAI   Releases   GPT Update!!!"
    assert first.url == "https://example.com/posts/openai-gpt"
    assert first.content == "Short summary about the release."
    assert first.source == "Fixture Source"
    assert first.category == "ai"
    assert first.weight == 80.0
    assert first.content_hash == title_content_hash(first.title)
    assert first.published_at == datetime(2025, 9, 4, 1, 30, tzinfo=timezone.utc)

    second = items[1]
    assert second.title == "Empty Body Story"
    assert second.url == "https://example.com/posts/empty-body"
    assert second.content is None
    news_pkg = Path(__file__).resolve().parents[1] / "app" / "news"
    for name in ("collector.py", "parser.py", "dedup.py"):
        src = (news_pkg / name).read_text(encoding="utf-8")
        assert "trafilatura" not in src
        assert "fetch_html" not in src


def test_dedup_url_update_skips_llm_and_title_hash_skip():
    item = NewsItem(
        title="Same Story Title",
        url="https://example.com/a",
        content="body-a",
        published_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
        source="S1",
        category="technology",
        weight=70.0,
        content_hash=title_content_hash("Same Story Title"),
    )
    session = session_scope()
    try:
        session.execute(delete(News))
        session.commit()

        first = apply_dedup(session, item)
        session.commit()
        assert first.action == "insert"
        assert first.needs_llm is True
        assert first.news is not None
        news_id = first.news.id

        again = apply_dedup(
            session,
            NewsItem(
                title="Same Story Title",
                url="https://example.com/a",
                content="body-a-updated",
                published_at=datetime(2025, 9, 2, tzinfo=timezone.utc),
                source="S1",
                category="technology",
                weight=70.0,
                content_hash=item.content_hash,
            ),
        )
        session.commit()
        assert again.action == "update"
        assert again.needs_llm is False
        assert again.reason == "url_exists"
        assert again.news is not None
        assert again.news.id == news_id
        assert again.news.content == "body-a-updated"
        assert again.news.published_at == datetime(2025, 9, 2, tzinfo=timezone.utc)

        title_dup = apply_dedup(
            session,
            NewsItem(
                title="Same Story Title!!!",
                url="https://example.com/b",
                content=None,
                published_at=None,
                source="S2",
                category="ai",
                weight=50.0,
                content_hash=title_content_hash("Same Story Title!!!"),
            ),
        )
        session.commit()
        assert title_dup.action == "skip"
        assert title_dup.needs_llm is False
        assert title_dup.reason == "title_hash_exists"
        rows = session.scalars(select(News)).all()
        assert len(rows) == 1
    finally:
        session.close()
