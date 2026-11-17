#!/usr/bin/env bash
# Small ext4 fixtures exercise installers and reject incomplete/stale payloads.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $EUID == 0 ]] || { echo 'Run with sudo or in a root user namespace.' >&2; exit 1; }
for feature in camera nfc gnss desktop locale sensors kernel-modules rtc; do
    python3 -B "tests/test-$feature-image.py"
done
