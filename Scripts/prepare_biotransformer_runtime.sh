#!/usr/bin/env bash
# Compatibility wrapper around the Python BioTransformer runtime helper.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/prepare_biotransformer_runtime.py" "$@"
