#!/bin/sh
set -eu

# Both scripts are idempotent and safe if several instances start together.
if [ "${GOVSCALE_RUN_INIT:-0}" = "1" ]; then
    : "${GOVSCALE_ADMIN_PASSWORD:?Set GOVSCALE_ADMIN_PASSWORD when GOVSCALE_RUN_INIT=1}"
    python scripts/seed_institutions.py
    python scripts/create_admin.py
fi

exec "$@"
