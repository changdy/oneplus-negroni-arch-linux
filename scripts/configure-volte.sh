#!/usr/bin/env bash
# Install the IMS data service the modem needs for VoLTE into a mounted rootfs.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-volte.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-volte.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
# 81voltd is prebuilt and links against these; mmcli gates its start.
for dependency in usr/lib/libmm-glib.so.0 usr/lib/libqrtr.so.1 usr/bin/mmcli usr/lib/polkit-1/polkitd; do
    test -e "$target_dir/$dependency"
done
mkdir -p "$log_dir"
rm -f "$log_dir/volte-sources.sha256" "$log_dir/volte-verification.json"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-volte"
fi
cd "$project_dir"
grep -Fxq "sha256 $(sha256sum config/volte/81voltd | cut -d' ' -f1)" config/volte/81voltd.source
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/systemd/system" "$target_dir/usr/local/libexec"
install -o 0 -g 0 -m 0755 config/volte/81voltd "$target_dir/usr/local/libexec/81voltd"
install -o 0 -g 0 -m 0644 config/systemd/negroni-81voltd.service \
    "$target_dir/etc/systemd/system/negroni-81voltd.service"
install -o 0 -g 0 -m 0755 config/volte/negroni-ims-recovery.py \
    "$target_dir/usr/local/libexec/negroni-ims-recovery.py"
install -o 0 -g 0 -m 0644 config/volte/negroni-ims-recovery.conf \
    "$target_dir/etc/negroni-ims-recovery.conf"
install -o 0 -g 0 -m 0644 config/systemd/negroni-ims-recovery.service \
    "$target_dir/etc/systemd/system/negroni-ims-recovery.service"
# polkitd reads this directory as group polkitd; keep the package's ownership.
test -d "$target_dir/etc/polkit-1/rules.d"
install -o 0 -g 0 -m 0644 config/volte/49-negroni-spacebar-bearers.rules \
    "$target_dir/etc/polkit-1/rules.d/49-negroni-spacebar-bearers.rules"
systemctl --root="$target_dir" enable negroni-81voltd.service negroni-ims-recovery.service
sha256sum config/volte/81voltd config/volte/81voltd.source config/volte/81voltd-negroni.patch \
    config/volte/49-negroni-spacebar-bearers.rules config/systemd/negroni-81voltd.service \
    config/volte/negroni-ims-recovery.py config/volte/negroni-ims-recovery.conf \
    config/systemd/negroni-ims-recovery.service \
    scripts/configure-volte.sh scripts/update-volte-image.sh scripts/verify-volte-image.py \
    > "$log_dir/volte-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/volte-sources.sha256"
