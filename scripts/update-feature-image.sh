#!/usr/bin/env bash
# Refresh one device feature in an existing image, in a private mount namespace.
set -euo pipefail
cd "$(dirname "$0")/.."
feature=${1:?Usage: update-feature-image.sh camera|nfc|gnss|desktop}
case "$feature" in camera|nfc|gnss|desktop) ;; *) exit 2 ;; esac
[[ $EUID == 0 ]] || { echo 'Run this script as root.' >&2; exit 1; }
image_dir=${IMAGE_DIR:-images}
log_dir=${LOG_DIR:-logs}
[[ -f "$image_dir/root.img" && -f "$log_dir/rootfs.complete" ]]
if [[ ${2:-} != --private-mounts ]]; then
    exec unshare --mount --propagation private bash "$0" "$feature" --private-mounts
fi
mkdir -p "$log_dir"
exec > >(tee "$log_dir/$feature-install.log") 2>&1
target_dir=$(mktemp -d /tmp/negroni-feature-image.XXXXXX)
cleanup() { umount "$target_dir" 2>/dev/null || true; rmdir "$target_dir" 2>/dev/null || true; }
trap cleanup EXIT
mount -o loop "$image_dir/root.img" "$target_dir"
bash "scripts/configure-$feature.sh" "$target_dir" "$log_dir"
sync -f "$target_dir"
umount "$target_dir"
python3 "scripts/verify-$feature-image.py" "$image_dir" "$log_dir"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/$feature-install.log" "$log_dir/$feature-verification.json"
