#!/usr/bin/env bash
# Install the USB debug gadget: NCM SSH at 10.55.0.1 and an ACM serial console.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-usb-debug.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-usb-debug.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
# NetworkManager's shared IPv4 method runs dnsmasq for the host side.
if [[ ! -x $target_dir/usr/bin/dnsmasq ]]; then
    printf 'dnsmasq is not installed in the rootfs\n' >&2
    exit 1
fi
mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-usb-debug"
fi
rm -f "$log_dir/usb-debug-sources.sha256" "$log_dir/usb-debug-verification.json"
install -d -o 0 -g 0 -m 0755 \
    "$target_dir/usr/local/bin" \
    "$target_dir/etc/systemd/system" \
    "$target_dir/etc/udev/rules.d"
install -d -o 0 -g 0 -m 0700 "$target_dir/etc/NetworkManager/system-connections"
install -o 0 -g 0 -m 0755 "$project_dir/config/usb-debug/usb-gadget.sh" \
    "$target_dir/usr/local/bin/usb-gadget.sh"
install -o 0 -g 0 -m 0644 "$project_dir/config/usb-debug/usb-gadget.service" \
    "$target_dir/etc/systemd/system/usb-gadget.service"
install -o 0 -g 0 -m 0644 "$project_dir/config/usb-debug/86-usb-debug-managed.rules" \
    "$target_dir/etc/udev/rules.d/86-usb-debug-managed.rules"
install -o 0 -g 0 -m 0600 "$project_dir/config/usb-debug/usb-debug.nmconnection" \
    "$target_dir/etc/NetworkManager/system-connections/usb-debug.nmconnection"
systemctl --root="$target_dir" enable usb-gadget.service serial-getty@ttyGS0.service
cd "$project_dir"
sha256sum config/usb-debug/usb-gadget.sh config/usb-debug/usb-gadget.service \
    config/usb-debug/86-usb-debug-managed.rules config/usb-debug/usb-debug.nmconnection \
    scripts/configure-usb-debug.sh scripts/verify-usb-debug-image.py \
    > "$log_dir/usb-debug-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/usb-debug-sources.sha256"
