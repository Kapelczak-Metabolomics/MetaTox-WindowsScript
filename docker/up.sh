#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f docker-compose.mac.yml ]] && [[ "$(uname -s)" == "Darwin" ]]; then
  exec docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build "$@"
fi

exec docker compose up --build "$@"
