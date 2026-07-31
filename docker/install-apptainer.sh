#!/usr/bin/env bash
set -euo pipefail

APPTAINER_VERSION="${APPTAINER_VERSION:-1.3.6}"
ARCH="${TARGETARCH:-$(dpkg --print-architecture)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_amd64_deb() {
  local base="apptainer_${APPTAINER_VERSION}_amd64.deb"
  local suid="apptainer-suid_${APPTAINER_VERSION}_amd64.deb"
  local url_base="https://github.com/apptainer/apptainer/releases/download/v${APPTAINER_VERSION}"
  local work_dir
  work_dir="$(mktemp -d)"

  echo "Installing Apptainer ${APPTAINER_VERSION} + apptainer-suid from GitHub (${ARCH})..."
  (
    cd "${work_dir}"
    wget -q "${url_base}/${base}"
    wget -q "${url_base}/${suid}"
    apt-get update
    apt-get install -y --no-install-recommends "./${base}" "./${suid}"
  )
  rm -rf "${work_dir}"
}

install_arm64_ppa() {
  echo "Installing Apptainer + apptainer-suid from Ubuntu PPA (${ARCH})..."
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates gnupg software-properties-common
  add-apt-repository -y ppa:apptainer/ppa
  apt-get update
  apt-get install -y --no-install-recommends apptainer apptainer-suid
}

case "${ARCH}" in
  amd64)
    install_amd64_deb
    ;;
  arm64)
    install_arm64_ppa
    ;;
  *)
    echo "Unsupported architecture for Apptainer install: ${ARCH}" >&2
    echo "On Apple Silicon Macs you can also build with:" >&2
    echo "  docker compose -f docker-compose.yml -f docker-compose.mac.yml build" >&2
    exit 1
    ;;
esac

rm -rf /var/lib/apt/lists/*
ln -sf /usr/bin/apptainer /usr/local/bin/singularity
if [[ -x "${SCRIPT_DIR}/configure-apptainer.sh" ]]; then
  "${SCRIPT_DIR}/configure-apptainer.sh"
else
  echo "WARNING: configure-apptainer.sh not found beside install-apptainer.sh" >&2
fi
apptainer --version
