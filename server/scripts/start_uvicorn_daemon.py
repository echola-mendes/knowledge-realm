#!/usr/bin/env python3
"""Detach uvicorn so it survives the parent shell."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path("/tmp/knowledge_realm_uvicorn.log")
PID_FILE = Path("/tmp/knowledge_realm_uvicorn.pid")
PYTHON = ROOT / ".venv" / "bin" / "python"


def main() -> int:
    if not PYTHON.exists():
        print(f"missing venv python: {PYTHON}", file=sys.stderr)
        return 1
    # free port 8000
    try:
        out = subprocess.check_output(["lsof", "-tiTCP:8000", "-sTCP:LISTEN"], text=True).strip()
    except subprocess.CalledProcessError:
        out = ""
    for pid in out.split():
        try:
            os.kill(int(pid), 9)
        except OSError:
            pass
    if out:
        time.sleep(1)

    log_f = open(LOG, "w")
    proc = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    # wait until listening or fail
    for _ in range(40):
        time.sleep(0.25)
        if proc.poll() is not None:
            print(LOG.read_text(), file=sys.stderr)
            return 1
        try:
            listeners = subprocess.check_output(["lsof", "-tiTCP:8000", "-sTCP:LISTEN"], text=True).strip()
        except subprocess.CalledProcessError:
            listeners = ""
        if listeners:
            print(f"started pid={proc.pid} listen={listeners}")
            return 0
    print("timeout waiting for port 8000", file=sys.stderr)
    print(LOG.read_text(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
