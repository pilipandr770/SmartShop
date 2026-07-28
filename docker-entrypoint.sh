#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "Waiting for database..."
  python - <<'PYEOF'
import os
import sys
import time
import psycopg2
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if not url.startswith("postgresql"):
    sys.exit(0)

parsed = urlparse(url)
for attempt in range(30):
    try:
        conn = psycopg2.connect(
            dbname=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
        )
        conn.close()
        print("Database is ready")
        break
    except psycopg2.OperationalError as e:
        print(f"Database not ready yet ({attempt + 1}/30): {e}")
        time.sleep(2)
else:
    print("Database did not become ready in time")
    sys.exit(1)
PYEOF

  echo "Applying database migrations..."
  flask db upgrade
fi

exec "$@"
