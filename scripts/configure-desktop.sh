#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-desktop.sh ROOTFS LOGS}")
log_dir=$(realpath -m -- "${2:?Usage: configure-desktop.sh ROOTFS LOGS}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-desktop"
fi
rm -f "$log_dir/desktop-sources.sha256" "$log_dir/desktop-verification.json"
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/xdg/autostart" "$target_dir/usr/local/libexec"
install -o 0 -g 0 -m 0644 "$project_dir/config/desktop/negroni-desktop-defaults.desktop" \
    "$target_dir/etc/xdg/autostart/negroni-desktop-defaults.desktop"
install -o 0 -g 0 -m 0644 "$project_dir/config/desktop/negroni-desktop-defaults.py" \
    "$target_dir/usr/local/libexec/negroni-desktop-defaults.py"
cd "$project_dir"
sha256sum config/desktop/* config/packages/common-tools.txt scripts/configure-desktop.sh \
    scripts/verify-desktop-image.py scripts/image_feature.py scripts/update-feature-image.sh \
    > "$log_dir/desktop-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/desktop-sources.sha256"
