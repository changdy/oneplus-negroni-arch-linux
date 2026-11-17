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
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/xdg/autostart" "$target_dir/usr/local/libexec" \
    "$target_dir/etc/modprobe.d" "$target_dir/usr/share/polkit-1/actions" \
    "$target_dir/usr/share/plasma/quicksettings" \
    "$target_dir/etc/systemd/user/app-org.kde.krdpserver.service.d"
install -o 0 -g 0 -m 0644 "$project_dir/config/desktop/negroni-desktop-defaults.desktop" \
    "$target_dir/etc/xdg/autostart/negroni-desktop-defaults.desktop"
install -o 0 -g 0 -m 0644 "$project_dir/config/desktop/negroni-desktop-defaults.py" \
    "$target_dir/usr/local/libexec/negroni-desktop-defaults.py"
install -o 0 -g 0 -m 0755 "$project_dir/config/desktop/negroni-krdp-server.py" \
    "$target_dir/usr/local/libexec/negroni-krdp-server.py"
install -o 0 -g 0 -m 0644 "$project_dir/config/desktop/krdpserverrc" "$target_dir/etc/xdg/krdpserverrc"
krdp_dropins="$target_dir/etc/systemd/user/app-org.kde.krdpserver.service.d"
install -o 0 -g 0 -m 0644 "$project_dir/config/desktop/krdp-session.conf" "$krdp_dropins/10-negroni-session.conf"
rm -f "$krdp_dropins/10-negroni-usb.conf"
install -o 0 -g 0 -m 0755 "$project_dir/config/quicksettings/negroni-hardware-control" \
    "$target_dir/usr/local/libexec/negroni-hardware-control"
install -o 0 -g 0 -m 0644 "$project_dir/config/quicksettings/org.negroni.hardware-control.policy" \
    "$target_dir/usr/share/polkit-1/actions/org.negroni.hardware-control.policy"
install -o 0 -g 0 -m 0644 "$project_dir/config/quicksettings/nxp-nci-off.conf" \
    "$target_dir/etc/modprobe.d/nxp-nci-off.conf"
for setting in nfc gyro gps krdp; do
    package="$target_dir/usr/share/plasma/quicksettings/org.negroni.quicksetting.$setting"
    install -d -o 0 -g 0 -m 0755 "$package/contents/ui"
    install -o 0 -g 0 -m 0644 "$project_dir/config/quicksettings/$setting/metadata.json" "$package/metadata.json"
    install -o 0 -g 0 -m 0644 "$project_dir/config/quicksettings/$setting/contents/ui/main.qml" "$package/contents/ui/main.qml"
done
cd "$project_dir"
sha256sum config/desktop/*.py config/desktop/*.desktop config/desktop/krdp-session.conf config/desktop/krdpserverrc \
    config/quicksettings/negroni-hardware-control \
    config/quicksettings/org.negroni.hardware-control.policy config/quicksettings/nxp-nci-off.conf \
    config/quicksettings/{nfc,gyro,gps,krdp}/metadata.json config/quicksettings/{nfc,gyro,gps,krdp}/contents/ui/main.qml \
    config/packages/common-tools.txt scripts/configure-desktop.sh \
    scripts/verify-desktop-image.py scripts/image_feature.py scripts/update-feature-image.sh \
    > "$log_dir/desktop-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/desktop-sources.sha256"
