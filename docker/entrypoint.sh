#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
cd "${APP_ROOT}"

"${APP_ROOT}/docker/bootstrap.sh"

python3 "${APP_ROOT}/web_app/job_worker.py" &
JOB_WORKER_PID=$!

cleanup() {
  kill "${JOB_WORKER_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec gunicorn \
  --chdir "${APP_ROOT}/web_app" \
  --bind "0.0.0.0:${METATOX_PORT:-8501}" \
  --workers 1 \
  --threads 1 \
  --timeout 3600 \
  --graceful-timeout 120 \
  --worker-tmp-dir /dev/shm \
  app:app
