#!/usr/bin/env bash
# Smoke-test nested Apptainer configuration inside the MetaTox container.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
TMP_TEST="${APP_ROOT}/tmp/singularity-smoke"
SMILES="CCO"
export BIOTRANSFORMER_RUNTIME="${BIOTRANSFORMER_RUNTIME:-/var/lib/metatox/biotransformer-runtime}"

export APPTAINER_NO_MOUNT="${APPTAINER_NO_MOUNT:-cwd,home,tmp,/etc/localtime}"
export SINGULARITY_NO_MOUNT="${SINGULARITY_NO_MOUNT:-cwd,home,tmp,/etc/localtime}"
unset APPTAINER_BINDPATH SINGULARITY_BINDPATH

mkdir -p "${TMP_TEST}"

echo "==> Apptainer version"
singularity --version

echo "==> SygMa image can execute"
mkdir -p "${TMP_TEST}/sygma-runtime/home" "${TMP_TEST}/sygma-runtime/eggs"
singularity run --no-mount cwd,home,tmp -B "${TMP_TEST}:/tmp" \
  --env "HOME=/tmp/sygma-runtime/home" \
  --env "PYTHON_EGG_CACHE=/tmp/sygma-runtime/eggs" \
  --env "TMPDIR=/tmp" \
  docker://3dechem/sygma "${SMILES}" -1 1 -2 1 > "${TMP_TEST}/smoke_sygma.sdf" 2>"${TMP_TEST}/smoke_sygma.log"
test -s "${TMP_TEST}/smoke_sygma.sdf"
echo "OK: SygMa produced ${TMP_TEST}/smoke_sygma.sdf"

echo "==> BioTransformer writable runtime can predict nicotine metabolites"
mkdir -p "${TMP_TEST}"
rm -f "${TMP_TEST}/smoke_biotrans.csv"
NICOTINE_SMILES='CN1CCC[C@H]1c2cccnc2'
chmod +x "${APP_ROOT}/Scripts/prepare_biotransformer_runtime.sh"
bash "${APP_ROOT}/Scripts/prepare_biotransformer_runtime.sh" run \
  --bt-type allHuman \
  --cmode 3 \
  --nstep 1 \
  --smiles "${NICOTINE_SMILES}" \
  --output "${TMP_TEST}/smoke_biotrans.csv" > "${TMP_TEST}/smoke_biotrans.log" 2>&1
test -s "${TMP_TEST}/smoke_biotrans.csv"
if grep -Eq "UnsatisfiedLinkError|JNA temporary directory|/tmp' is not writable|Exception in thread" "${TMP_TEST}/smoke_biotrans.log"; then
  echo "BioTransformer Java/JNA failure:" >&2
  tail -n 80 "${TMP_TEST}/smoke_biotrans.log" >&2
  exit 1
fi
ROW_COUNT="$(tail -n +2 "${TMP_TEST}/smoke_biotrans.csv" | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
if [ "${ROW_COUNT}" -le 0 ]; then
  echo "BioTransformer predicted zero metabolites for nicotine:" >&2
  tail -n 80 "${TMP_TEST}/smoke_biotrans.log" >&2
  exit 1
fi
echo "OK: BioTransformer produced ${ROW_COUNT} metabolite row(s) in ${TMP_TEST}/smoke_biotrans.csv"

echo "==> GLORYx helper can query the public API"
python3 "${APP_ROOT}/Scripts/gloryx_api.py" \
  --phase phase_1_and_2 \
  --smile "${SMILES}" \
  --output "${TMP_TEST}/smoke_gloryx.csv" > "${TMP_TEST}/smoke_gloryx.log" 2>&1
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
