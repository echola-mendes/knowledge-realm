"""MinIO 软依赖测试：key 前缀分离、未配置降级。"""
from __future__ import annotations

from app.travel import minio_store


class FakeMinio:
    def __init__(self, *args, **kwargs):
        self.puts: list[tuple[str, str]] = []
        self.exists = False

    def bucket_exists(self, bucket):
        return self.exists

    def make_bucket(self, bucket):
        self.exists = True

    def put_object(self, bucket, key, data, length=None, content_type=None):
        assert length is not None and length > 0
        assert "html" in (content_type or "")
        self.puts.append((bucket, key))

    def presigned_get_object(self, bucket, key, expires=None):
        return f"http://minio.local/{bucket}/{key}"


def test_put_plan_html_key_prefix(monkeypatch):
    fake = FakeMinio()
    monkeypatch.setattr(minio_store, "minio_ready", lambda: True)
    monkeypatch.setattr(minio_store, "_client", lambda: fake)
    out = minio_store.put_plan_html("convo-123", "<html>方案</html>")
    assert out is not None
    bucket, key = fake.puts[0]
    assert key.startswith("plans/convo-123/")
    assert key.endswith(".html")
    assert out["url"].startswith("http://minio.local/")


def test_put_report_html_prefix_separated(monkeypatch):
    fake = FakeMinio()
    monkeypatch.setattr(minio_store, "minio_ready", lambda: True)
    monkeypatch.setattr(minio_store, "_client", lambda: fake)
    out = minio_store.put_report_html("convo-123", "<html>报告</html>")
    bucket, key = fake.puts[0]
    assert key.startswith("reports/convo-123/")
    assert out["key"] == key


def test_not_ready_returns_none(monkeypatch):
    monkeypatch.setattr(minio_store, "minio_ready", lambda: False)
    assert minio_store.put_plan_html("c", "<html></html>") is None
    assert minio_store.put_report_html("c", "<html></html>") is None


def test_upload_failure_returns_none(monkeypatch):
    class Broken(FakeMinio):
        def put_object(self, *a, **kw):
            raise RuntimeError("disk full")

    monkeypatch.setattr(minio_store, "minio_ready", lambda: True)
    monkeypatch.setattr(minio_store, "_client", lambda: Broken())
    assert minio_store.put_plan_html("c", "<html></html>") is None
