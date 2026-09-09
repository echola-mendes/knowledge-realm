#!/usr/bin/env python3
"""Run Alembic upgrade without server/alembic shadowing the alembic package."""
from __future__ import annotations

import sys
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[1]
sys.path = [p for p in sys.path if Path(p).resolve() != _SERVER]

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def main() -> None:
    cfg = Config(str(_SERVER / "alembic.ini"))
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
