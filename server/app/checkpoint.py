from __future__ import annotations

from app.config import get_settings

_pool = None
_checkpointer = None


def psycopg_conninfo() -> str:
    raw = get_settings().database_url.strip()
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw.removeprefix("postgresql+psycopg://")
    return raw


def get_checkpointer():
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    _pool = ConnectionPool(
        conninfo=psycopg_conninfo(),
        min_size=1,
        max_size=10,
        timeout=30,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "connect_timeout": 10},
    )
    _checkpointer = PostgresSaver(_pool)
    _checkpointer.setup()
    return _checkpointer


def reset_checkpointer() -> None:
    global _pool, _checkpointer
    _checkpointer = None
    if _pool is not None:
        _pool.close()
        _pool = None
