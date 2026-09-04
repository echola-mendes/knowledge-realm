from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.config import reset_settings  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models import ScheduledTask, TaskExecution  # noqa: E402
from app.services import task_service as ts  # noqa: E402
from app.worker.queue import QueueUnavailableError, enqueue  # noqa: E402

PYTHON = ROOT / ".venv" / "bin" / "python3.12"


def wait_worker_started(proc: subprocess.Popen[str], timeout: float = 10) -> str:
    buf: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            rest = proc.stdout.read() if proc.stdout else ""
            raise SystemExit(f"worker exited early:\n{''.join(buf)}{rest}")
        assert proc.stdout is not None
        line = proc.stdout.readline()
        if line:
            buf.append(line)
            if "Starting worker" in line:
                return "".join(buf)
        else:
            time.sleep(0.05)
    raise SystemExit(f"worker did not start:\n{''.join(buf)}")


def latest_execution(session, task_id: int) -> TaskExecution:
    return session.scalars(
        select(TaskExecution)
        .where(TaskExecution.task_id == task_id)
        .order_by(TaskExecution.id.desc())
    ).first()


def main() -> None:
    proc = subprocess.Popen(
        [str(PYTHON), "-u", "-m", "app.worker.worker"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    execution = None
    session = session_scope()
    try:
        logs = wait_worker_started(proc)
        print("worker_started", "process_task" in logs)

        task = session.scalar(select(ScheduledTask).where(ScheduledTask.task_type == "NEWS_REFRESH"))
        if task is None:
            raise SystemExit("missing NEWS_REFRESH seed task")
        execution = ts.create_execution(session, task.id)
        asyncio.run(
            enqueue(
                {
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "run_id": execution.run_id,
                }
            )
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            session.refresh(execution)
            if execution.status in (ts.STATUS_SUCCESS, ts.STATUS_FAILED):
                break
            time.sleep(0.2)
        print("status", execution.status, "result", execution.result)
        if execution.status != ts.STATUS_SUCCESS:
            raise SystemExit("execution did not become SUCCESS")
        if not execution.result or execution.result.get("news_pipeline_pending") is not True:
            raise SystemExit("result.news_pipeline_pending is not true")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if execution is not None:
            row = session.get(TaskExecution, execution.id)
            if row is not None:
                session.delete(row)
                session.commit()
        session.close()

    original = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
    reset_settings()
    try:
        asyncio.run(enqueue({"task_id": 1, "task_type": "NEWS_REFRESH", "run_id": "x"}))
        raise SystemExit("expected QueueUnavailableError")
    except QueueUnavailableError as exc:
        print("unavailable_ok", str(exc))
    finally:
        if original is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = original
        reset_settings()
    print("ok")


if __name__ == "__main__":
    main()
