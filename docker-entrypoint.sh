#!/bin/sh
set -eu

# GovScale uses PostgreSQL only.
# Schema creation/migration occurs during application startup.
# Baseline seed data and admin creation are handled by Compose one-shot services.

exec "$@"
