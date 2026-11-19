#!/usr/bin/env bash
# Install PMIC counter restoration and NTP-backed offset persistence.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-rtc.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-rtc.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
test -x "$target_dir/usr/bin/python3"
test -x "$target_dir/usr/lib/systemd/systemd-timesyncd"

mkdir -p "$log_dir"
rm -f "$log_dir/rtc-sources.sha256"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-rtc"
fi
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/systemd/system" \
    "$target_dir/usr/local/libexec" "$target_dir/var/lib/negroni-rtc"
install -o 0 -g 0 -m 0755 "$project_dir/config/rtc/negroni-rtc-clock" \
    "$target_dir/usr/local/libexec/negroni-rtc-clock"
for unit in negroni-rtc-sync.path negroni-rtc-sync.service negroni-rtc-restore.service; do
    install -o 0 -g 0 -m 0644 "$project_dir/config/systemd/$unit" "$target_dir/etc/systemd/system/$unit"
done
systemctl --root="$target_dir" enable negroni-rtc-sync.path negroni-rtc-restore.service
[[ $(systemctl --root="$target_dir" is-enabled negroni-rtc-sync.path) == enabled ]]
[[ $(systemctl --root="$target_dir" is-enabled negroni-rtc-restore.service) == enabled ]]

cd "$project_dir"
sha256sum config/rtc/negroni-rtc-clock config/systemd/negroni-rtc-sync.path \
    config/systemd/negroni-rtc-sync.service config/systemd/negroni-rtc-restore.service \
    scripts/configure-rtc.sh scripts/update-rtc-image.sh \
    scripts/verify-rtc-image.py scripts/image_feature.py > "$log_dir/rtc-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/rtc-sources.sha256"
