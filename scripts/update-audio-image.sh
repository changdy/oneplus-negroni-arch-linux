#!/usr/bin/env bash
# Install or refresh the Negroni audio topology and UCM in an existing root.img.
set -euo pipefail
cd "$(dirname "$0")/.."
project_dir=$PWD
image_dir=${IMAGE_DIR:-images}
log_dir=${LOG_DIR:-logs}
[[ $EUID == 0 ]] || { echo 'Run this script as root.' >&2; exit 1; }
[[ -f "$image_dir/root.img" && -f "$log_dir/rootfs.complete" ]]
if [[ ${1:-} != --private-mounts ]]; then
    exec unshare --mount --propagation private bash "$0" --private-mounts
fi
mkdir -p "$log_dir"
exec > >(tee "$log_dir/audio-install.log") 2>&1
export LC_ALL=C
target_dir=$(mktemp -d /tmp/negroni-audio-image.XXXXXX)
cleanup() {
    umount "$target_dir" 2>/dev/null || true
    rmdir "$target_dir" 2>/dev/null || true
}
trap cleanup EXIT
mount -o loop "$image_dir/root.img" "$target_dir"
bash "$project_dir/scripts/configure-audio.sh" "$target_dir" "$log_dir"
sync -f "$target_dir/usr/share/alsa/ucm2/OnePlus/negroni/HiFi.conf"
umount "$target_dir"
python3 scripts/verify-audio-image.py "$image_dir" "$log_dir"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/audio-install.log" \
    "$log_dir/audio-verification.json"
