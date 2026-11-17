#!/usr/bin/env bash
# Set the default language and generate the matching glibc locale.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-locale.sh ROOTFS LOGS}")
log_dir=$(realpath -m -- "${2:?Usage: configure-locale.sh ROOTFS LOGS}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
test -f "$target_dir/etc/locale.gen"
test -x "$target_dir/usr/bin/locale-gen"

mkdir -p "$log_dir"
rm -f "$log_dir/locale-sources.sha256" "$log_dir/locale-verification.json"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-locale"
fi
install -o 0 -g 0 -m 0644 "$project_dir/config/locale/locale.conf" "$target_dir/etc/locale.conf"
sed -i -E \
    -e 's/^#?[[:space:]]*en_US\.UTF-8[[:space:]]+UTF-8[[:space:]]*$/en_US.UTF-8 UTF-8/' \
    -e 's/^#?[[:space:]]*zh_CN\.UTF-8[[:space:]]+UTF-8[[:space:]]*$/zh_CN.UTF-8 UTF-8/' \
    "$target_dir/etc/locale.gen"
grep -Fxq 'en_US.UTF-8 UTF-8' "$target_dir/etc/locale.gen"
grep -Fxq 'zh_CN.UTF-8 UTF-8' "$target_dir/etc/locale.gen"
chroot "$target_dir" locale-gen
chroot "$target_dir" localedef --list-archive | grep -Fxq zh_CN.utf8

cd "$project_dir"
sha256sum config/locale/locale.conf scripts/configure-locale.sh \
    scripts/update-locale-image.sh scripts/verify-locale-image.py > "$log_dir/locale-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/locale-sources.sha256"
