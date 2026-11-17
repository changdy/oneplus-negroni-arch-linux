#!/usr/bin/env bash
# Compatibility entry point for the GPU policy installer.
set -euo pipefail
exec bash "$(dirname "$0")/configure-gpu-runtime-pm.sh" "$@"
