from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from http_client import api_client  # noqa: E402

from app.config import reset_settings  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models import TaskExecution  # noqa: E402
from app.services.task_service import REGISTERED_TASK_TYPES  # noqa: E402

PYTHON = ROOT / ".venv" / "bin" / "python3.12"
DUMMY_TYPE = "STEP5_DUMMY"


def _start_worker() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(PYTHON), "-u", "-m", "app.worker.worker"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def _stop_worker(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    with api_client() as client:
        listed = client.get("/api/tasks")
        assert listed.status_code == 200, listed.text
        tasks = listed.json()
        assert any(t["task_type"] == "NEWS_REFRESH" for t in tasks), tasks
        seed = next(t for t in tasks if t["task_type"] == "NEWS_REFRESH")
        seed_id = seed["id"]
        print("list_ok", seed_id)

        types = client.get("/api/tasks/types")
        assert types.status_code == 200, types.text
        assert any(t["task_type"] == "NEWS_REFRESH" for t in types.json())

        dup = client.post(
            "/api/tasks",
            json={
                "name": "dup",
                "task_type": "NEWS_REFRESH",
                "schedule_type": "INTERVAL",
                "schedule_config": {"minutes": 30},
            },
        )
        assert dup.status_code == 409, dup.text
        print("post_conflict_ok")

        renamed = client.put(f"/api/tasks/{seed_id}", json={"name": "tmp-step5"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "tmp-step5"
        restored = client.put(f"/api/tasks/{seed_id}", json={"name": seed["name"]})
        assert restored.status_code == 200, restored.text
        print("put_ok")

        REGISTERED_TASK_TYPES[DUMMY_TYPE] = {"label": "dummy", "handler": "none"}
        dummy_id = None
        try:
            created = client.post(
                "/api/tasks",
                json={
                    "name": "step5-dummy",
                    "task_type": DUMMY_TYPE,
                    "schedule_type": "INTERVAL",
                    "schedule_config": {"minutes": 60},
                    "enabled": False,
                },
            )
            assert created.status_code == 201, created.text
            dummy_id = created.json()["id"]
            deleted = client.delete(f"/api/tasks/{dummy_id}")
            assert deleted.status_code == 200, deleted.text
            dummy_id = None
            print("create_delete_ok")
        finally:
            REGISTERED_TASK_TYPES.pop(DUMMY_TYPE, None)
            if dummy_id is not None:
                client.delete(f"/api/tasks/{dummy_id}")

        run = client.post(f"/api/tasks/{seed_id}/run")
        assert run.status_code == 200, run.text
        body = run.json()
        assert "execution_id" in body and "run_id" in body, body
        execution_id = body["execution_id"]
        execs = client.get(f"/api/tasks/{seed_id}/executions")
        assert execs.status_code == 200, execs.text
        latest = execs.json()[0]
        assert latest["id"] == execution_id
        assert latest["status"] == "PENDING"
        print("run_pending_ok", execution_id)

        proc = _start_worker()
        try:
            deadline = time.time() + 20
            status = latest["status"]
            while time.time() < deadline:
                rows = client.get(f"/api/tasks/{seed_id}/executions").json()
                row = next(r for r in rows if r["id"] == execution_id)
                status = row["status"]
                if status in ("SUCCESS", "FAILED"):
                    latest = row
                    break
                time.sleep(0.2)
            assert status == "SUCCESS", latest
            assert latest["result"] and latest["result"].get("news_pipeline_pending") is True
            print("run_async_ok", status)
        finally:
            _stop_worker(proc)

        original = os.environ.get("REDIS_URL")
        os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
        reset_settings()
        failed_id = None
        try:
            unavailable = client.post(f"/api/tasks/{seed_id}/run")
            assert unavailable.status_code == 503, unavailable.text
            assert "Redis" in unavailable.json()["detail"]
            failed_id = client.get(f"/api/tasks/{seed_id}/executions").json()[0]["id"]
            print("run_503_ok")
        finally:
            if original is None:
                os.environ.pop("REDIS_URL", None)
            else:
                os.environ["REDIS_URL"] = original
            reset_settings()
            if failed_id is not None:
                session = session_scope()
                try:
                    row = session.get(TaskExecution, failed_id)
                    if row is not None:
                        session.delete(row)
                        session.commit()
                finally:
                    session.close()
    print("ok")


if __name__ == "__main__":
    main()
