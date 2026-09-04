from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".venv" / "lib" / "python3.12" / "site-packages"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.main import create_app, reset_app_state  # noqa: E402
from app.models import ScheduledTask, TaskExecution  # noqa: E402
from app.scheduler.scheduler import get_scheduler  # noqa: E402


def main() -> None:
    reset_app_state()
    app = create_app()
    with TestClient(app) as _client:
        jobs = get_scheduler().get_jobs()
        print("jobs", [j.id for j in jobs])
        if not jobs:
            raise SystemExit("no scheduler jobs")
        session = session_scope()
        try:
            task = session.scalar(select(ScheduledTask).where(ScheduledTask.task_type == "NEWS_REFRESH"))
            assert task is not None
            expected = f"task-{task.id}"
            if expected not in [j.id for j in jobs]:
                raise SystemExit(f"missing job {expected}")
            job = get_scheduler().get_job(expected)
            asyncio.run(job.func(**job.kwargs))
            execs = list(
                session.scalars(
                    select(TaskExecution)
                    .where(TaskExecution.task_id == task.id)
                    .order_by(TaskExecution.id.desc())
                )
            )
            print("latest_status", execs[0].status, execs[0].run_id)
            if execs[0].status not in ("PENDING", "SUCCESS"):
                raise SystemExit("enqueue did not create execution")
            session.delete(execs[0])
            session.commit()
        finally:
            session.close()
    print("ok")


if __name__ == "__main__":
    main()
