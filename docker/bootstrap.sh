#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
CACHE_DIR="${SINGULARITY_CACHEDIR:-/var/lib/metatox/singularity-cache}"

mkdir -p "${CACHE_DIR}" "${APP_ROOT}/data/input" "${APP_ROOT}/data/output" "${APP_ROOT}/log"
export SINGULARITY_CACHEDIR="${CACHE_DIR}"
export APPTAINER_CACHEDIR="${CACHE_DIR}"

if command -v dos2unix >/dev/null 2>&1; then
  find "${APP_ROOT}" -type f -name "*.sh" -exec dos2unix -q {} + 2>/dev/null || true
fi

if command -v apptainer >/dev/null 2>&1 && ! command -v singularity >/dev/null 2>&1; then
  ln -sf "$(command -v apptainer)" /usr/local/bin/singularity
fi

if command -v singularity >/dev/null 2>&1; then
  singularity remote add --no-login SylabsCloud cloud.sycloud.io >/dev/null 2>&1 || true
fi

chmod +x "${APP_ROOT}/Metatox.sh"

if [[ "${METATOX_PREFETCH_IMAGES:-false}" == "true" ]]; then
  echo "Prefetching Singularity images (this can take several minutes)..."
  singularity pull -F docker://3dechem/sygma >/dev/null 2>&1 || true
  singularity pull -F \
    https://depot.galaxyproject.org/singularity/biotransformer:3.0.20230403--hdfd78af_0 \
    >/dev/null 2>&1 || true
fi

echo "MetaTox container bootstrap complete."
