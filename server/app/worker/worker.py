from __future__ import annotations

import logging

from arq.worker import run_worker

from app.worker.settings import WorkerSettings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
