#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
cd "${APP_ROOT}"

"${APP_ROOT}/docker/bootstrap.sh"

exec streamlit run "${APP_ROOT}/web_app/app.py" \
  --server.port="${METATOX_PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
