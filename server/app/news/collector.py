from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.news.sources import NewsSource

_USER_AGENT = "knowledge-realm-news/1.0"


@dataclass(frozen=True)
class CollectResult:
    source: NewsSource
    body: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.body is not None


def collect_source(
    source: NewsSource,
    *,
    timeout: float | None = None,
    client: httpx.Client | None = None,
) -> CollectResult:
    """Fetch one feed URL. Network failures are returned as error, not raised."""
    seconds = float(timeout if timeout is not None else get_settings().news_http_timeout)
    owns_client = client is None
    http = client or httpx.Client(
        timeout=seconds,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )
    try:
        response = http.get(source.url)
        response.raise_for_status()
        return CollectResult(source=source, body=response.text)
    except httpx.TimeoutException:
        return CollectResult(source=source, error="timeout")
    except httpx.HTTPError as exc:
        return CollectResult(source=source, error=f"http_error:{exc.__class__.__name__}")
    except Exception as exc:  # noqa: BLE001 — per-source isolation
        return CollectResult(source=source, error=f"fetch_failed:{exc.__class__.__name__}")
    finally:
        if owns_client:
            http.close()


def collect_sources(
    sources: list[NewsSource],
    *,
    timeout: float | None = None,
) -> list[CollectResult]:
    """Fetch many sources; a single failure does not stop the rest."""
    seconds = float(timeout if timeout is not None else get_settings().news_http_timeout)
    results: list[CollectResult] = []
    with httpx.Client(
        timeout=seconds,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        for source in sources:
            results.append(collect_source(source, timeout=seconds, client=client))
    return results
