"""MinIO 对象存储（软依赖）：行程方案页 plans/ 与知识报告 reports/ 前缀分离。

未配置（缺 MINIO_ENDPOINT 或 minio 包未安装）时所有 put_* 返回 None 并附原因，
调用方据此降级提示，不得影响 SSE 实时输出。
"""
from __future__ import annotations

import datetime as _dt
import io
import uuid

from app.config import get_settings

PLAN_PREFIX = "plans"
REPORT_PREFIX = "reports"

_client_cache: object | None = None


def minio_ready() -> bool:
    settings = get_settings()
    return bool(settings.minio_endpoint and settings.minio_access_key and settings.minio_secret_key)


def _client():
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    if not minio_ready():
        return None
    try:
        from minio import Minio
    except ImportError:
        return None
    settings = get_settings()
    _client_cache = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return _client_cache


def reset_client_cache() -> None:
    global _client_cache
    _client_cache = None


def _put_html(prefix: str, conversation_id: str | None, html: str) -> dict | None:
    client = _client()
    if client is None:
        return None
    settings = get_settings()
    convo = conversation_id or uuid.uuid4().hex
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    key = f"{prefix}/{convo}/{stamp}.html"
    data = html.encode("utf-8")
    try:
        found = client.bucket_exists(settings.minio_bucket)
        if not found:
            client.make_bucket(settings.minio_bucket)
        client.put_object(
            settings.minio_bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type="text/html; charset=utf-8",
        )
        try:
            url = client.presigned_get_object(
                settings.minio_bucket, key, expires=_dt.timedelta(days=7)
            )
        except Exception:
            url = None
        return {"key": key, "url": url, "bucket": settings.minio_bucket}
    except Exception:
        return None


def put_plan_html(conversation_id: str | None, html: str) -> dict | None:
    """方案页上传：key = plans/{conversation_id}/{timestamp}.html。"""
    return _put_html(PLAN_PREFIX, conversation_id, html)


def put_report_html(conversation_id: str | None, html: str) -> dict | None:
    """知识报告上传：key = reports/{conversation_id}/{timestamp}.html（与方案页前缀分离）。"""
    return _put_html(REPORT_PREFIX, conversation_id, html)
