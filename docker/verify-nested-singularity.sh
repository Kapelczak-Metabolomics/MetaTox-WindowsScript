#!/usr/bin/env bash
# Smoke-test nested Apptainer configuration inside the MetaTox container.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
TMP_TEST="${APP_ROOT}/tmp/singularity-smoke"
SMILES="CCO"

export APPTAINER_NO_MOUNT="${APPTAINER_NO_MOUNT:-cwd,home,tmp,/etc/localtime}"
export SINGULARITY_NO_MOUNT="${SINGULARITY_NO_MOUNT:-cwd,home,tmp,/etc/localtime}"
unset APPTAINER_BINDPATH SINGULARITY_BINDPATH

mkdir -p "${TMP_TEST}"

echo "==> Apptainer version"
singularity --version

echo "==> GLORYx image can access gloryx_api.py"
singularity run --no-mount cwd,home,tmp -B "${TMP_TEST}:/tmp" \
  library://abourdais/default/gloryx_api \
  --phase phase_1 \
  --smile "${SMILES}" \
  --output "/tmp/smoke_gloryx.csv"
test -s "${TMP_TEST}/smoke_gloryx.csv"
echo "OK: GLORYx produced ${TMP_TEST}/smoke_gloryx.csv"

echo "==> MetaTrans image can execute"
singularity run --no-mount cwd,home,tmp --containall -B "${TMP_TEST}:/tmp" --writable-tmpfs \
  library://abourdais/default/metatrans \
  -n smoke \
  -s "${SMILES}" \
  -r /tmp/smoke_metatrans.csv \
  -l /tmp/smoke_metatrans.log
test -s "${TMP_TEST}/smoke_metatrans.csv"
echo "OK: MetaTrans produced ${TMP_TEST}/smoke_metatrans.csv"

rm -rf "${TMP_TEST}"
echo "All nested Singularity smoke tests passed."
