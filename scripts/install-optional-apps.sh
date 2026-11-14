#!/usr/bin/env bash
# Run on the ARM64 phone when a user elects to install a profile.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
case "${1:-}" in
    --help|-h|'')
        echo 'Usage: sudo bash scripts/install-optional-apps.sh diagnostics|sunshine'
        exit 0 ;;
    diagnostics|sunshine) profile=$1 ;;
    *) echo 'Unknown optional profile.' >&2; exit 2 ;;
esac
[[ $EUID == 0 && $(uname -m) == aarch64 ]] || {
    echo 'Run with sudo on the aarch64 phone.' >&2; exit 1;
}
if [[ $profile == diagnostics ]]; then
    mapfile -t packages < "$project_dir/config/packages/optional-diagnostics.txt"
    pacman -S --needed "${packages[@]}"
    # Install only for the invoking desktop user and keep an existing custom page.
    if [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
        account=$(getent passwd "$SUDO_USER")
        IFS=: read -r _ _ uid gid _ user_home _ <<< "$account"
        page=$user_home/.local/share/plasma-systemmonitor/overview.page
        if [[ ! -e $page ]]; then
            install -d -o "$uid" -g "$gid" -m 0755 "$(dirname "$page")"
            install -o "$uid" -g "$gid" -m 0644 "$project_dir/config/optional/overview.page" "$page"
        fi
    fi
    echo 'Diagnostics installed. qpwgraph is for inspection; follow docs/audio.md before changing routes.'
    exit 0
fi
version=2026.914.233613
name=Sunshine_${version}_aarch64.AppImage
expected=d352134d9e6161ac1e3d7d1699fb0e5eff0a3460eee4d5cc131d52b04cb91152
destination=/opt/negroni-sunshine/$version
[[ ! -e $destination ]] || { echo "$destination already exists; keep the current installation."; exit 1; }
pacman -S --needed curl patchelf libcap
work=$(mktemp -d /tmp/negroni-sunshine.XXXXXX)
trap 'rm -rf "$work"' EXIT
curl --fail --location --retry 3 --connect-timeout 15 \
    "https://github.com/SunshineStream/Sunshine/releases/download/v$version/$name" -o "$work/$name"
printf '%s  %s\n' "$expected" "$work/$name" | sha256sum --check
chmod 0755 "$work/$name"
(cd "$work" && "./$name" --appimage-extract >/dev/null)
install -d -o 0 -g 0 -m 0755 "$destination"
cp -a "$work/squashfs-root/." "$destination/"
chown -R 0:0 "$destination"
# File capabilities suppress LD_LIBRARY_PATH; the absolute RUNPATH is required.
patchelf --set-rpath "$destination/usr/lib" "$destination/usr/bin/sunshine"
(cd "$destination" && ./usr/bin/sunshine --version)
install -D -o 0 -g 0 -m 0644 "$destination/usr/share/sunshine/udev/rules.d/60-sunshine.rules" \
    /etc/udev/rules.d/60-sunshine.rules
install -D -o 0 -g 0 -m 0644 "$destination/usr/share/sunshine/modules-load.d/60-sunshine.conf" \
    /etc/modules-load.d/60-sunshine.conf
setcap cap_sys_admin,cap_sys_nice+p "$destination/usr/bin/sunshine"
install -D -o 0 -g 0 -m 0644 "$project_dir/config/optional/negroni-sunshine.service" \
    /usr/lib/systemd/user/negroni-sunshine.service
install -D -o 0 -g 0 -m 0644 "$project_dir/config/optional/sunshine.desktop" /usr/local/share/applications/sunshine.desktop
install -D -o 0 -g 0 -m 0644 "$destination/usr/share/icons/hicolor/256x256/apps/sunshine.png" \
    /usr/local/share/icons/hicolor/256x256/apps/sunshine.png
modprobe uinput
modprobe uhid
udevadm control --reload-rules
udevadm trigger --property-match=DEVNAME=/dev/uinput
udevadm trigger --property-match=DEVNAME=/dev/uhid
echo 'Installed. In the graphical user session run:'
echo '  systemctl --user daemon-reload'
echo '  systemctl --user enable --now negroni-sunshine.service'
echo 'Open Sunshine in the application launcher and set your own web credentials.'
