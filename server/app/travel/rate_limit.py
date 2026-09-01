"""进程内 sliding window 写限流：用户维度 30 次 / 60 秒。

未用 Redis；单机部署足够。重启进程清空窗口。
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from threading import Lock

_WINDOW_SECONDS = 60
_WRITE_LIMIT_PER_WINDOW = 30

_windows: dict[str, deque[float]] = {}
_lock = Lock()


class RateLimitedError(Exception):
    """写操作超过 30/min 限制。"""


def check_write_rate(user_id: uuid.UUID | str) -> None:
    """检查并记录一次写操作；超限抛出 RateLimitedError（调用方应返回 429）。"""
    key = str(user_id)
    now = time.monotonic()
    with _lock:
        window = _windows.get(key)
        if window is None:
            window = deque()
            _windows[key] = window
        cutoff = now - _WINDOW_SECONDS
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= _WRITE_LIMIT_PER_WINDOW:
            raise RateLimitedError("预订写操作过于频繁，请稍后再试（限流 30 次/分钟）")
        window.append(now)


def reset_rate_limit() -> None:
    global _windows
    with _lock:
        _windows.clear()
