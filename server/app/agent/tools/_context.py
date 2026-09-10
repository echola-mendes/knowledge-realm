from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig


def configurable(config: RunnableConfig | None) -> dict[str, Any]:
    if not config:
        return {}
    raw = config.get("configurable") or {}
    return raw if isinstance(raw, dict) else {}


def as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def tool_runtime(config: RunnableConfig | None) -> tuple[object | None, uuid.UUID | None, uuid.UUID | None, int]:
    cfg = configurable(config)
    session = cfg.get("session")
    user_id = as_uuid(cfg.get("user_id"))
    knowledge_base_id = as_uuid(cfg.get("knowledge_base_id"))
    k_raw = cfg.get("tool_k", 5)
    try:
        k = int(k_raw)
    except (TypeError, ValueError):
        k = 5
    if k <= 0:
        k = 5
    return session, user_id, knowledge_base_id, k
