#!/usr/bin/env bash
# Refresh the default language in an existing root.img.
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
exec > >(tee "$log_dir/locale-install.log") 2>&1
export LC_ALL=C
target_dir=$(mktemp -d /tmp/negroni-locale-image.XXXXXX)
cleanup() {
    umount -R "$target_dir/dev" 2>/dev/null || true
    umount "$target_dir/proc" 2>/dev/null || true
    umount "$target_dir" 2>/dev/null || true
    rmdir "$target_dir" 2>/dev/null || true
}
trap cleanup EXIT
mount -o loop "$image_dir/root.img" "$target_dir"
mkdir -p "$target_dir/proc" "$target_dir/dev"
mount -t proc proc "$target_dir/proc"
mount --rbind /dev "$target_dir/dev"
mount --make-rslave "$target_dir/dev"
if ! chroot "$target_dir" /bin/true; then
    /usr/lib/systemd/systemd-binfmt /usr/lib/binfmt.d/qemu-aarch64.conf
    chroot "$target_dir" /bin/true
fi
bash "$project_dir/scripts/configure-locale.sh" "$target_dir" "$project_dir/$log_dir"
sync -f "$target_dir/usr/lib/locale/locale-archive"
umount -R "$target_dir/dev"
umount "$target_dir/proc"
umount "$target_dir"
python3 scripts/verify-locale-image.py "$image_dir" "$log_dir"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/locale-install.log" \
    "$log_dir/locale-verification.json"
