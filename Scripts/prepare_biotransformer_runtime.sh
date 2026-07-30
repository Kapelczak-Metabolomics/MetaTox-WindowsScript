#!/usr/bin/env bash
# Prepare a writable BioTransformer runtime and run predictions.
# Nested Apptainer inside Docker Desktop often cannot use on-image DB files
# even with --writable-tmpfs; copying jar/database/supportfiles to a bind-mounted
# writable directory and running with --pwd there is reliable.
set -euo pipefail

BIOTRANSFORMER_IMAGE="${BIOTRANSFORMER_IMAGE:-https://depot.galaxyproject.org/singularity/biotransformer:3.0.20230403--hdfd78af_0}"
BIOTRANSFORMER_RUNTIME="${BIOTRANSFORMER_RUNTIME:-/var/lib/metatox/biotransformer-runtime}"

usage() {
  cat <<'EOF'
Usage:
  prepare_biotransformer_runtime.sh prepare
  prepare_biotransformer_runtime.sh run --bt-type TYPE --cmode N --nstep N --smiles SMILES --output CSV
EOF
}

find_singularity() {
  if command -v singularity >/dev/null 2>&1; then
    command -v singularity
    return 0
  fi
  if command -v apptainer >/dev/null 2>&1; then
    command -v apptainer
    return 0
  fi
  echo "ERROR: singularity/apptainer not found" >&2
  return 1
}

prepare_runtime() {
  local runtime="${BIOTRANSFORMER_RUNTIME}"
  local marker="${runtime}/.ready"
  local singularity
  singularity="$(find_singularity)"

  mkdir -p "${runtime}"
  if [ -f "${marker}" ] && compgen -G "${runtime}/*.jar" >/dev/null; then
    echo "BioTransformer runtime ready: ${runtime}"
    return 0
  fi

  echo "Extracting BioTransformer jar/database/supportfiles into ${runtime} ..."
  find "${runtime}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  mkdir -p "${runtime}"

  "${singularity}" exec \
    --no-mount cwd,home,tmp \
    --writable-tmpfs \
    -B "${runtime}:/bt-export" \
    "${BIOTRANSFORMER_IMAGE}" \
    bash -lc '
      set -euo pipefail
      src=""
      if command -v biotransformer >/dev/null 2>&1; then
        script="$(readlink -f "$(command -v biotransformer)")"
        src="$(dirname "${script}")"
      fi
      if [ -z "${src}" ] || [ ! -d "${src}" ]; then
        src="$(ls -d /usr/local/share/biotransformer-* 2>/dev/null | head -n 1 || true)"
      fi
      if [ -z "${src}" ] || [ ! -d "${src}" ]; then
        echo "ERROR: could not locate BioTransformer package directory inside the image" >&2
        ls -la /usr/local/share >&2 || true
        exit 1
      fi
      echo "Copying from ${src}"
      cp -a "${src}/." /bt-export/
      ls -la /bt-export | head
    '

  if ! compgen -G "${runtime}/*.jar" >/dev/null; then
    echo "ERROR: BioTransformer jar was not extracted into ${runtime}" >&2
    ls -la "${runtime}" >&2 || true
    return 1
  fi

  chmod -R u+rwX "${runtime}" || true
  touch "${marker}"
  echo "BioTransformer runtime prepared: ${runtime}"
}

run_prediction() {
  local bt_type="" cmode="3" nstep="1" smiles="" output=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --bt-type) bt_type="$2"; shift 2 ;;
      --cmode) cmode="$2"; shift 2 ;;
      --nstep) nstep="$2"; shift 2 ;;
      --smiles) smiles="$2"; shift 2 ;;
      --output) output="$2"; shift 2 ;;
      *) echo "Unknown argument: $1" >&2; usage; return 1 ;;
    esac
  done

  if [ -z "${bt_type}" ] || [ -z "${smiles}" ] || [ -z "${output}" ]; then
    usage
    return 1
  fi

  prepare_runtime

  local runtime="${BIOTRANSFORMER_RUNTIME}"
  local jar
  jar="$(ls "${runtime}"/*.jar | head -n 1)"
  local jar_name
  jar_name="$(basename "${jar}")"
  local singularity
  singularity="$(find_singularity)"
  local out_dir
  out_dir="$(cd "$(dirname "${output}")" && pwd)"
  local out_name
  out_name="$(basename "${output}")"
  mkdir -p "${out_dir}"
  rm -f "${output}"

  # Run from the writable extracted package so relative database/supportfiles resolve.
  # Bind the same writable out dir as /tmp for JNA native libraries.
  "${singularity}" exec \
    --no-mount cwd,home,tmp \
    --writable-tmpfs \
    --pwd /bt \
    -B "${runtime}:/bt" \
    -B "${out_dir}:/bt-out" \
    -B "${out_dir}:/tmp" \
    --env "TMPDIR=/tmp" \
    --env "JNA_TMPDIR=/tmp" \
    "${BIOTRANSFORMER_IMAGE}" \
    java -Xms512m -Xmx6g \
      -Djava.io.tmpdir=/tmp \
      -Djna.tmpdir=/tmp \
      -jar "/bt/${jar_name}" \
      -b "${bt_type}" \
      -k "pred" \
      -cm "${cmode}" \
      -s "${nstep}" \
      -ismi "${smiles}" \
      -ocsv "/bt-out/${out_name}"

  if [ ! -s "${output}" ]; then
    echo "ERROR: BioTransformer did not write ${output}" >&2
    return 1
  fi
}

cmd="${1:-}"
if [ $# -gt 0 ]; then
  shift
fi

case "${cmd}" in
  prepare) prepare_runtime ;;
  run) run_prediction "$@" ;;
  *) usage; exit 1 ;;
esac
