#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os
import sys
import time

import psycopg

raw = os.environ["DATABASE_URL"]
url = raw.replace("postgresql+psycopg://", "postgresql://", 1)

for _ in range(60):
    try:
        psycopg.connect(url).close()
        break
    except Exception:
        time.sleep(1)
else:
    sys.exit("database unavailable after 60s")
PY

echo "Running migrations..."
cd /app/server
python scripts/alembic_upgrade.py

exec "$@"
