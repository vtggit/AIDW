#!/usr/bin/env bash
# Backend startup script — waits for PostgreSQL, runs migrations, then starts the app.
#
# Usage (inside Docker):
#   ENTRYPOINT ["/app/start.sh"]
#   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
#
# Startup flow:
#   1. Wait for PostgreSQL to accept connections
#   2. Run Alembic migrations (alembic upgrade head)
#   3. Hand off to the CMD (uvicorn)
#
# This ensures schema versioning is deliberate and repeatable.
#
# Failure modes:
#   - Database unreachable: script exits with code 1 after MAX_ATTEMPTS
#   - Migration failure: script exits with code 1, logs migration error
#   - Application start failure: uvicorn handles its own errors

set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-aicrm}"

MAX_ATTEMPTS=30
SLEEP_INTERVAL=2

attempt=0
echo "[startup] Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT} (database: ${DB_NAME}) ..."

while [ $attempt -lt $MAX_ATTEMPTS ]; do
    if python -c "
import psycopg2
try:
    conn = psycopg2.connect(host='${DB_HOST}', port=${DB_PORT}, dbname='${DB_NAME}', user='${DB_USER}', password='${DB_PASSWORD}')
    conn.close()
    exit(0)
except Exception as e:
    print(f'Connection failed: {e}', flush=True)
    exit(1)
" 2>&1; then
        echo "[startup] PostgreSQL is ready."
        break
    fi

    attempt=$((attempt + 1))
    echo "[startup]   attempt ${attempt}/${MAX_ATTEMPTS} — waiting ${SLEEP_INTERVAL}s ..."
    sleep $SLEEP_INTERVAL
done

if [ $attempt -ge $MAX_ATTEMPTS ]; then
    echo "[startup] ERROR: PostgreSQL at ${DB_HOST}:${DB_PORT} did not become ready in time." >&2
    echo "[startup] ERROR: Database '${DB_NAME}' is unreachable after ${MAX_ATTEMPTS} attempts." >&2
    echo "[startup] ERROR: Check that the database is running and DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD are correct." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Run Alembic migrations
# ---------------------------------------------------------------------------
echo "[startup] Running database migrations ..."
cd /app
if alembic upgrade head 2>&1; then
    echo "[startup] Migrations complete."
else
    MIGRATION_EXIT=$?
    echo "[startup] ERROR: Database migrations failed with exit code ${MIGRATION_EXIT}." >&2
    echo "[startup] ERROR: The application will NOT start. Fix the migration error before proceeding." >&2
    echo "[startup] ERROR: Check alembic logs above for the specific migration that failed." >&2
    echo "[startup] ERROR: Common causes: stale schema, missing migration files, or database permissions." >&2
    exit $MIGRATION_EXIT
fi

# ---------------------------------------------------------------------------
# Start the application
# ---------------------------------------------------------------------------
echo "[startup] Starting application server ..."
exec "$@"
