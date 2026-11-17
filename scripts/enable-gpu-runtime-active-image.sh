#!/usr/bin/env bash
# Compatibility entry point for old build instructions.
set -euo pipefail
exec bash "$(dirname "$0")/update-gpu-runtime-pm-image.sh" "$@"
