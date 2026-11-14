#!/usr/bin/env bash
# Install the exact AFW fix deployed on NE2210; positioning stays on demand.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-gnss.sh ROOTFS LOGS}")
log_dir=$(realpath -m -- "${2:?Usage: configure-gnss.sh ROOTFS LOGS}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
test -x "$target_dir/usr/bin/qmicli"
test -x "$target_dir/usr/bin/qrtr-lookup"
mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-gnss"
fi
rm -f "$log_dir/gnss-sources.sha256" "$log_dir/gnss-verification.json"
(cd "$project_dir/config/gnss/runtime" && sha256sum --check SHA256SUMS)
install -d -o 0 -g 0 -m 0755 "$target_dir/opt/negroni-gnss/"{sbin,lib} \
    "$target_dir/etc/systemd/system/ModemManager.service.d" "$target_dir/usr/local/libexec" \
    "$target_dir/usr/share/licenses/negroni-gnss"
install -o 0 -g 0 -m 0755 "$project_dir/config/gnss/runtime/ModemManager" \
    "$target_dir/opt/negroni-gnss/sbin/ModemManager"
install -o 0 -g 0 -m 0755 "$project_dir/config/gnss/runtime/libqmi-glib.so.5.12.0" \
    "$target_dir/opt/negroni-gnss/lib/libqmi-glib.so.5.12.0"
ln -sfn libqmi-glib.so.5.12.0 "$target_dir/opt/negroni-gnss/lib/libqmi-glib.so.5"
install -o 0 -g 0 -m 0644 "$project_dir/config/gnss/20-negroni-gnss.conf" \
    "$target_dir/etc/systemd/system/ModemManager.service.d/20-negroni-gnss.conf"
install -o 0 -g 0 -m 0644 "$project_dir/config/gnss/negroni-gnss-unlock.service" \
    "$target_dir/etc/systemd/system/negroni-gnss-unlock.service"
install -o 0 -g 0 -m 0755 "$project_dir/scripts/gnss-assist.py" \
    "$target_dir/usr/local/libexec/negroni-gnss-assist.py"
install -o 0 -g 0 -m 0644 "$project_dir/config/gnss/runtime/"COPYING* \
    "$project_dir/config/gnss/sources.txt" "$target_dir/usr/share/licenses/negroni-gnss/"
# Loading this binary verifies the rootfs ABI; it does not start the modem daemon.
chroot "$target_dir" /usr/bin/env LD_LIBRARY_PATH=/opt/negroni-gnss/lib \
    /opt/negroni-gnss/sbin/ModemManager --version
systemctl --root="$target_dir" enable negroni-gnss-unlock.service
cd "$project_dir"
sha256sum config/gnss/runtime/* config/gnss/*.patch config/gnss/*.conf config/gnss/*.service \
    config/gnss/sources.txt scripts/gnss-assist.py scripts/build-gnss-stack.sh \
    scripts/configure-gnss.sh scripts/verify-gnss-image.py scripts/image_feature.py \
    scripts/update-feature-image.sh > "$log_dir/gnss-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/gnss-sources.sha256"
