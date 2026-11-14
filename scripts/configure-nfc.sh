#!/usr/bin/env bash
# Install the SN100 clock fallback. The driver is built by the kernel config.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-nfc.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-nfc.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
mkdir -p "$log_dir"
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/modprobe.d"
install -o 0 -g 0 -m 0644 "$project_dir/config/nfc/nxp-nci.conf" \
    "$target_dir/etc/modprobe.d/nxp-nci.conf"
cd "$project_dir"
sha256sum config/nfc/nxp-nci.conf scripts/configure-nfc.sh > "$log_dir/nfc-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/nfc-sources.sha256"
