#!/usr/bin/env sh
# Run the test-suite against a throwaway PostgreSQL database.
# Usage: export POSTGRES_PASSWORD=<letters-and-digits>; sh scripts/test_postgres.sh [pytest args]
set -eu
cd "$(dirname "$0")/.."

: "${POSTGRES_PASSWORD:?Export POSTGRES_PASSWORD first}"
export GOVSCALE_SECRET_KEY="${GOVSCALE_SECRET_KEY:-test-only-secret-key}"
export GOVSCALE_ADMIN_PASSWORD="${GOVSCALE_ADMIN_PASSWORD:-test-only-admin-pass}"
PORT_ON_HOST="${GOVSCALE_PG_HOST_PORT:-5433}"

docker compose up -d --wait db
docker compose exec -T db psql -U govscale -d postgres \
    -c "DROP DATABASE IF EXISTS govscale_test WITH (FORCE)" \
    -c "CREATE DATABASE govscale_test"

GOVSCALE_TEST_DATABASE_URI="postgresql+psycopg2://govscale:${POSTGRES_PASSWORD}@127.0.0.1:${PORT_ON_HOST}/govscale_test" \
    python -m pytest -q "$@"
