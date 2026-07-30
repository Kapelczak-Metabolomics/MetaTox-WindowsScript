#!/usr/bin/env bash
# Configure Apptainer for nested execution inside Docker.
set -euo pipefail

find_starter_suid() {
  find /usr /opt -name starter-suid 2>/dev/null | head -n 1
}

configure_conf() {
  local conf="/etc/apptainer/apptainer.conf"
  if [[ ! -f "${conf}" ]]; then
    return 0
  fi

  if grep -q '^allow setuid' "${conf}"; then
    sed -i 's/^allow setuid = no/allow setuid = yes/' "${conf}" || true
  else
    echo 'allow setuid = yes' >> "${conf}"
  fi

  if grep -q '^allow user namespaces' "${conf}"; then
    sed -i 's/^allow user namespaces = no/allow user namespaces = yes/' "${conf}" || true
  else
    echo 'allow user namespaces = yes' >> "${conf}"
  fi
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

  if unshare --user true 2>/dev/null; then
    echo "  user namespaces: available"
  else
    echo "  user namespaces: unavailable (setuid fallback required)"
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

configure_conf
configure_setuid_starter || true
diagnose_runtime
