#!/usr/bin/env bash
# Run the AICRM backend test suite against a containerized PostgreSQL.
#
# Usage:
#   cd backend
#   ./run_tests.sh              # run all tests
#   ./run_tests.sh -k test_auth # pass extra pytest args
#
# This script:
#   1. Starts an ephemeral PostgreSQL container (no persistent volume)
#   2. Waits for it to be ready
#   3. Runs pytest with DB_PORT=5433 (test container)
#   4. Tears down the container
#
# Requires: docker (no sudo apt install postgresql)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
TEST_DB_PORT=5433
TEST_DB_SERVICE="test-db"

# ---------------------------------------------------------------------------
# Default environment variables for the test database
# (override by setting these in your shell or .env file)
# ---------------------------------------------------------------------------
export DB_NAME="${DB_NAME:-aicrm}"
export DB_USER="${DB_USER:-aicrm}"
export DB_PASSWORD="${DB_PASSWORD:-change-me-in-production}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# shellcheck disable=SC2317,SC2329  # cleanup + its body run via the 'trap cleanup EXIT' below
cleanup() {
    echo ""
    echo "==> Stopping test database container..."
    docker compose -f "$COMPOSE_FILE" -p aicrm-test rm -f "$TEST_DB_SERVICE" >/dev/null 2>&1 || true
}

trap cleanup EXIT

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if ! command -v docker &>/dev/null; then
    echo "ERROR: docker is not installed or not in PATH"
    exit 1
fi

# ---------------------------------------------------------------------------
# Start the ephemeral test database
# ---------------------------------------------------------------------------

echo "==> Starting ephemeral test database on port $TEST_DB_PORT..."
docker compose -f "$COMPOSE_FILE" -p aicrm-test up -d "$TEST_DB_SERVICE"

echo "==> Waiting for PostgreSQL to be ready..."
# Wait up to 30 seconds for the DB to accept connections
for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" -p aicrm-test exec -T "$TEST_DB_SERVICE" \
        pg_isready -U aicrm -d aicrm &>/dev/null; then
        echo "==> PostgreSQL is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: PostgreSQL did not become ready in time"
        exit 1
    fi
    sleep 1
done

# ---------------------------------------------------------------------------
# Run pytest
# ---------------------------------------------------------------------------

echo "==> Running backend tests..."

# Export test DB and auth config so conftest.py picks them up at import time
export DB_HOST="localhost"
export DB_PORT="$TEST_DB_PORT"
export AUTH_MODE="development"
export AUTH_DEV_TOKEN="dev-secret-token"

cd "$SCRIPT_DIR"
python3 -m pytest tests/ -v --tb=short "$@"
EXIT_CODE=$?

# ---------------------------------------------------------------------------
# Exit
# ---------------------------------------------------------------------------

if [ "$EXIT_CODE" -eq 0 ]; then
    echo ""
    echo "==> All tests passed."
else
    echo ""
    echo "==> Some tests failed (exit code $EXIT_CODE)."
fi

exit "$EXIT_CODE"
