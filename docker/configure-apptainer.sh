#!/usr/bin/env bash
# Configure Apptainer for nested execution inside Docker.
set -euo pipefail

find_starter_suid() {
  find /usr /opt -name starter-suid 2>/dev/null | head -n 1
}

set_apptainer_conf() {
  local key="$1"
  local value="$2"
  local conf="/etc/apptainer/apptainer.conf"

  if [[ ! -f "${conf}" ]]; then
    return 0
  fi

  local escaped_key
  escaped_key="$(printf '%s' "${key}" | sed 's/[.[*^$()+?{|]/\\&/g')"
  if grep -qE "^[[:space:]]*${escaped_key}[[:space:]]*=" "${conf}"; then
    sed -i "s/^[[:space:]]*${escaped_key}[[:space:]]*=.*/${key} = ${value}/" "${conf}"
  else
    printf '\n%s = %s\n' "${key}" "${value}" >> "${conf}"
  fi
}

configure_conf() {
  # Nested Docker cannot create user namespaces reliably (especially on Docker Desktop).
  # Force the setuid starter shipped in apptainer-suid instead.
  set_apptainer_conf "allow setuid" "yes"
  set_apptainer_conf "allow user ns" "no"
  set_apptainer_conf "allow user namespaces" "no"
}

configure_setuid_starter() {
  local starter
  starter="$(find_starter_suid || true)"
  if [[ -z "${starter}" ]]; then
    echo "WARNING: apptainer-suid starter not found. Install the apptainer-suid package." >&2
    return 1
  fi

  if chmod u+s "${starter}" 2>/dev/null; then
    echo "Apptainer setuid starter enabled: ${starter}"
    return 0
  fi

  echo "WARNING: Could not enable setuid bit on ${starter}" >&2
  return 1
}

diagnose_runtime() {
  echo "Apptainer runtime diagnostics:"
  if command -v apptainer >/dev/null 2>&1; then
    apptainer --version || true
  elif command -v singularity >/dev/null 2>&1; then
    singularity --version || true
  fi

  if [[ -f /etc/apptainer/apptainer.conf ]]; then
    grep -E '^allow (setuid|user ns|user namespaces)' /etc/apptainer/apptainer.conf || true
  fi

  if unshare --user true 2>/dev/null; then
    echo "  user namespaces: available (Apptainer configured to ignore them)"
  else
    echo "  user namespaces: unavailable (Apptainer setuid mode required)"
  fi

  local starter
  starter="$(find_starter_suid || true)"
  if [[ -n "${starter}" ]] && [[ -u "${starter}" ]]; then
    echo "  setuid starter: ready (${starter})"
  elif [[ -n "${starter}" ]]; then
    echo "  setuid starter: present but not setuid (${starter})"
  else
    echo "  setuid starter: missing"
  fi
}

verify_apptainer_exec() {
  local test_log="/tmp/apptainer-runtime-check.log"
  local smiles="CCO"

  if ! command -v singularity >/dev/null 2>&1; then
    echo "ERROR: singularity/apptainer command not found." >&2
    return 1
  fi

  export APPTAINER_NO_MOUNT="${APPTAINER_NO_MOUNT:-cwd,home,tmp,/etc/localtime}"
  export SINGULARITY_NO_MOUNT="${SINGULARITY_NO_MOUNT:-cwd,home,tmp,/etc/localtime}"
  unset APPTAINER_BINDPATH SINGULARITY_BINDPATH

  echo "Running Apptainer runtime check..."
  if timeout 180 singularity exec --no-mount cwd,home,tmp docker://alpine:3.19 echo ok >"${test_log}" 2>&1; then
    echo "Apptainer runtime check: OK"
    return 0
  fi

  echo "ERROR: Apptainer runtime check failed. Nested Singularity cannot run in this Docker setup." >&2
  sed 's/^/  /' "${test_log}" >&2 || true
  echo "  Start MetaTox with: docker compose up --build" >&2
  echo "  Do not use plain docker run unless you pass --privileged and the security options from docker-compose.yml." >&2
  return 1
}

configure_conf
configure_setuid_starter || true
diagnose_runtime

if [[ "${METATOX_VERIFY_APPTAINER:-true}" == "true" ]]; then
  verify_apptainer_exec
fi
