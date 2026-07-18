#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
CACHE_DIR="${SINGULARITY_CACHEDIR:-/var/lib/metatox/singularity-cache}"

mkdir -p "${CACHE_DIR}" "${APP_ROOT}/data/input" "${APP_ROOT}/data/output" "${APP_ROOT}/log" /tmp
export SINGULARITY_CACHEDIR="${CACHE_DIR}"
export APPTAINER_CACHEDIR="${CACHE_DIR}"
export APPTAINER_NO_MOUNT="${APPTAINER_NO_MOUNT:-/etc/localtime}"
export SINGULARITY_NO_MOUNT="${SINGULARITY_NO_MOUNT:-/etc/localtime}"
export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-/tmp/apptainer}"
export SINGULARITY_TMPDIR="${SINGULARITY_TMPDIR:-/tmp/apptainer}"
export TMPDIR="${TMPDIR:-/tmp}"
mkdir -p "${APPTAINER_TMPDIR}" "${APP_ROOT}/data/job"

if [ ! -e /etc/localtime ] && [ -f /usr/share/zoneinfo/UTC ]; then
  ln -sf /usr/share/zoneinfo/UTC /etc/localtime
fi

if command -v dos2unix >/dev/null 2>&1; then
  find "${APP_ROOT}" -type f -name "*.sh" -exec dos2unix -q {} + 2>/dev/null || true
fi

if command -v apptainer >/dev/null 2>&1 && ! command -v singularity >/dev/null 2>&1; then
  ln -sf "$(command -v apptainer)" /usr/local/bin/singularity
fi

if command -v singularity >/dev/null 2>&1; then
  echo "Apptainer version: $(singularity --version)"
  singularity remote add --no-login SylabsCloud cloud.sycloud.io >/dev/null 2>&1 || true
  singularity remote use SylabsCloud >/dev/null 2>&1 || true
else
  echo "WARNING: Singularity/Apptainer was not found."
fi

chmod +x "${APP_ROOT}/Metatox.sh"

pull_image() {
  local label="$1"
  shift
  echo "  Pulling ${label}..."
  if singularity pull -F "$@"; then
    echo "  OK: ${label}"
    return 0
  fi
  echo "  WARNING: failed to prefetch ${label}"
  return 1
}

if [[ "${METATOX_PREFETCH_IMAGES:-false}" == "true" ]]; then
  echo "Prefetching Singularity images (this can take several minutes)..."
  prefetch_failures=0
  pull_image "SygMa" docker://3dechem/sygma || prefetch_failures=$((prefetch_failures + 1))
  pull_image "BioTransformer" \
    https://depot.galaxyproject.org/singularity/biotransformer:3.0.20230403--hdfd78af_0 \
    || prefetch_failures=$((prefetch_failures + 1))
  pull_image "RDKit" library://abourdais/default/rdkit || prefetch_failures=$((prefetch_failures + 1))
  pull_image "GLORYx" library://abourdais/default/gloryx_api || prefetch_failures=$((prefetch_failures + 1))
  pull_image "MetaTrans" library://abourdais/default/metatrans || prefetch_failures=$((prefetch_failures + 1))
  if [ "${prefetch_failures}" -gt 0 ]; then
    echo "WARNING: ${prefetch_failures} image(s) failed to prefetch. They will download on first use."
  fi
fi

echo "MetaTox container bootstrap complete."
