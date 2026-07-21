#!/usr/bin/env bash
set -euo pipefail

APPTAINER_VERSION="${APPTAINER_VERSION:-1.3.6}"
ARCH="${TARGETARCH:-$(dpkg --print-architecture)}"

install_amd64_deb() {
  local deb="apptainer_${APPTAINER_VERSION}_amd64.deb"
  local url="https://github.com/apptainer/apptainer/releases/download/v${APPTAINER_VERSION}/${deb}"

  echo "Installing Apptainer ${APPTAINER_VERSION} from GitHub (${ARCH})..."
  wget -q "${url}"
  apt-get update
  apt-get install -y --no-install-recommends "./${deb}"
  rm -f "./${deb}"
}

install_arm64_ppa() {
  echo "Installing Apptainer from Ubuntu PPA (${ARCH})..."
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates gnupg software-properties-common
  add-apt-repository -y ppa:apptainer/ppa
  apt-get update
  apt-get install -y --no-install-recommends apptainer
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
apptainer --version
