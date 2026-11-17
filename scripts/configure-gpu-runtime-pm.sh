#!/usr/bin/env bash
# Install delayed automatic GPU runtime PM and a manual forced-active fallback.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-gpu-runtime-pm.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-gpu-runtime-pm.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
test -x "$target_dir/usr/bin/sh"
mkdir -p "$log_dir"
rm -f "$log_dir/gpu-runtime-pm-sources.sha256" "$log_dir/gpu-runtime-pm.complete" \
    "$log_dir/gpu-runtime-pm-verification.json"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-gpu-runtime-pm"
fi
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/systemd/system"
for unit in gpu-runtime-pm.service gpu-runtime-active.service; do
    install -o 0 -g 0 -m 0644 "$project_dir/config/systemd/$unit" "$target_dir/etc/systemd/system/$unit"
done
systemctl --root="$target_dir" disable gpu-runtime-active.service
systemctl --root="$target_dir" enable gpu-runtime-pm.service
[[ $(systemctl --root="$target_dir" is-enabled gpu-runtime-active.service) == disabled ]]
[[ $(systemctl --root="$target_dir" is-enabled gpu-runtime-pm.service) == enabled ]]
printf '%s\n' 'GPU runtime PM policy: auto; autosuspend delay: 1000 ms' \
    'Device: /sys/bus/platform/devices/3d00000.gpu' \
    'Enabled: gpu-runtime-pm.service; manual fallback: gpu-runtime-active.service (disabled)' \
    > "$log_dir/gpu-runtime-pm-config.txt"
cd "$project_dir"
sha256sum config/systemd/gpu-runtime-pm.service config/systemd/gpu-runtime-active.service \
    scripts/configure-gpu-runtime-pm.sh scripts/update-gpu-runtime-pm-image.sh \
    scripts/verify-gpu-runtime-pm-image.py > "$log_dir/gpu-runtime-pm-sources.sha256"
touch "$log_dir/gpu-runtime-pm.complete"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/gpu-runtime-pm-sources.sha256" \
    "$log_dir/gpu-runtime-pm-config.txt" "$log_dir/gpu-runtime-pm.complete"
