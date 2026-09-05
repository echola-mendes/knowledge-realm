#!/usr/bin/env python3
"""Detach arq worker into its own session."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "worker.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

with LOG.open("a", encoding="utf-8") as log:
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.worker.worker"],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

print(f"pid={proc.pid}")
