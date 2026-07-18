#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
cd "${APP_ROOT}"

"${APP_ROOT}/docker/bootstrap.sh"

exec gunicorn \
  --chdir "${APP_ROOT}/web_app" \
  --bind "0.0.0.0:${METATOX_PORT:-8501}" \
  --workers 1 \
  --threads 4 \
  --timeout 3600 \
  app:app
