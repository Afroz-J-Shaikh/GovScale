#!/bin/bash
# Beanstalk postdeploy hook (template). deploy-eb.yml fills in the __PLACEHOLDERS__
# and ships it inside the bundle as .platform/hooks/postdeploy/01_init.sh.
#
# Runs seed_institutions.py and create_admin.py in a throwaway container.
# The admin password is fetched from Secrets Manager here and never stored in
# the Beanstalk environment or in the long-running web container.
# Both scripts are idempotent, so running on every deploy / every instance is safe.
set -euo pipefail

IMAGE="__IMAGE__"
REGION="__REGION__"
SECRET_ID="__SECRET_ID__"

cfg() { /opt/elasticbeanstalk/bin/get-config environment -k "$1"; }

export GOVSCALE_SECRET_KEY="$(cfg GOVSCALE_SECRET_KEY)"
export GOVSCALE_DATABASE_URI="$(cfg GOVSCALE_DATABASE_URI)"
export GOVSCALE_ADMIN_EMAIL="$(cfg GOVSCALE_ADMIN_EMAIL)"
GOVSCALE_ADMIN_PASSWORD="$(aws secretsmanager get-secret-value \
  --region "$REGION" --secret-id "$SECRET_ID" \
  --query SecretString --output text \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["admin_password"])')"
export GOVSCALE_ADMIN_PASSWORD

# "-e NAME" (no value) passes the variable without putting it in the process arguments.
# The image was already pulled by Beanstalk during this deployment.
docker run --rm \
  --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp --tmpfs /app/instance \
  -e GOVSCALE_SECRET_KEY -e GOVSCALE_DATABASE_URI \
  -e GOVSCALE_ADMIN_EMAIL -e GOVSCALE_ADMIN_PASSWORD \
  "$IMAGE" sh -c 'python scripts/seed_institutions.py && python scripts/create_admin.py'