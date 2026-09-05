from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from app.config import REPO_ROOT, get_settings

ALLOWED_CATEGORIES = frozenset({"technology", "ai", "finance"})
ALLOWED_TYPES = frozenset({"rss", "atom", "api"})


class NewsSourcesError(Exception):
    """Invalid news sources file or entry."""


@dataclass(frozen=True)
class NewsSource:
    id: str
    name: str
    url: str
    type: str
    category: str
    weight: float
    enabled: bool


def resolve_sources_path(raw: str | Path | None = None) -> Path:
    if raw is None:
        return get_settings().news_sources_path
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def _require_str(entry: dict, key: str, *, index: int) -> str:
    value = entry.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise NewsSourcesError(f"sources[{index}]: missing required field `{key}`")
    if not isinstance(value, str):
        raise NewsSourcesError(f"sources[{index}]: `{key}` must be a string")
    return value.strip()


def _parse_entry(raw: object, *, index: int) -> NewsSource:
    if not isinstance(raw, dict):
        raise NewsSourcesError(f"sources[{index}]: expected mapping, got {type(raw).__name__}")

    source_id = _require_str(raw, "id", index=index)
    name = _require_str(raw, "name", index=index)
    url = _require_str(raw, "url", index=index)
    source_type = _require_str(raw, "type", index=index).lower()
    category = _require_str(raw, "category", index=index).lower()

    if source_type not in ALLOWED_TYPES:
        raise NewsSourcesError(
            f"sources[{index}] ({source_id}): invalid type `{source_type}`; "
            f"allowed: {sorted(ALLOWED_TYPES)}"
        )
    if category not in ALLOWED_CATEGORIES:
        raise NewsSourcesError(
            f"sources[{index}] ({source_id}): invalid category `{category}`; "
            f"allowed: {sorted(ALLOWED_CATEGORIES)}"
        )

    weight_raw = raw.get("weight", 0)
    try:
        weight = float(weight_raw)
    except (TypeError, ValueError) as exc:
        raise NewsSourcesError(
            f"sources[{index}] ({source_id}): weight must be a number"
        ) from exc
    if weight < 0 or weight > 100:
        raise NewsSourcesError(
            f"sources[{index}] ({source_id}): weight must be between 0 and 100"
        )

    enabled_raw = raw.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise NewsSourcesError(
            f"sources[{index}] ({source_id}): enabled must be a boolean"
        )

    return NewsSource(
        id=source_id,
        name=name,
        url=url,
        type=source_type,
        category=category,
        weight=weight,
        enabled=enabled_raw,
    )


def load_sources(
    path: str | Path | None = None,
    *,
    categories: Iterable[str] | None = None,
    enabled_only: bool = True,
) -> list[NewsSource]:
    """Load and validate news sources from YAML.

    Path is resolved relative to the repository root when not absolute.
    Raises NewsSourcesError on missing file or invalid schema.
    """
    resolved = resolve_sources_path(path)
    if not resolved.is_file():
        raise NewsSourcesError(f"news sources file not found: {resolved}")

    try:
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise NewsSourcesError(f"invalid YAML in {resolved}: {exc}") from exc

    if data is None:
        raise NewsSourcesError(f"{resolved}: empty file")
    if not isinstance(data, dict):
        raise NewsSourcesError(f"{resolved}: root must be a mapping with `sources`")

    raw_sources = data.get("sources")
    if raw_sources is None:
        raise NewsSourcesError(f"{resolved}: missing `sources` list")
    if not isinstance(raw_sources, list):
        raise NewsSourcesError(f"{resolved}: `sources` must be a list")

    parsed = [_parse_entry(item, index=i) for i, item in enumerate(raw_sources)]

    category_filter: set[str] | None = None
    if categories is not None:
        category_filter = {c.strip().lower() for c in categories if c and str(c).strip()}
        unknown = category_filter - ALLOWED_CATEGORIES
        if unknown:
            raise NewsSourcesError(
                f"invalid filter categories: {sorted(unknown)}; "
                f"allowed: {sorted(ALLOWED_CATEGORIES)}"
            )

    result: list[NewsSource] = []
    for source in parsed:
        if enabled_only and not source.enabled:
            continue
        if category_filter is not None and source.category not in category_filter:
            continue
        result.append(source)
    return result
