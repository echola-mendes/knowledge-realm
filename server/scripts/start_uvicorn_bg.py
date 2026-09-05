#!/usr/bin/env python3
"""Detach uvicorn into its own session so shell wrappers cannot kill it."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "uvicorn.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

with LOG.open("a", encoding="utf-8") as log:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

print(f"pid={proc.pid}")
