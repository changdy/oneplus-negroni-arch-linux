#!/usr/bin/env bash
# Explicit opt-in to the three experimental cameras; no boot-time loading.
set -euo pipefail
case ${1:-} in
    load|unload) action=$1;;
    --help|-h) echo 'Usage: negroni-camera-extra.sh load|unload'; exit 0;;
    *) echo 'Usage: negroni-camera-extra.sh load|unload'; exit 2;;
esac
[[ $EUID == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
source "$(dirname "$0")/negroni-camera-idle.sh"
exec 9>/run/lock/negroni-camera-capture.lock
flock -n 9 || { echo 'Another camera operation is running.' >&2; exit 1; }
negroni_camera_require_idle
base=/usr/lib/negroni/camera
if [[ $action == unload ]]; then
    rmmod negroni_camera_overlay
    rmmod negroni_extra_sensors
    rmmod imx615
    exit 0
fi
for name in imx615 negroni_extra_sensors negroni_camera_overlay; do
    [[ ! -d /sys/module/$name ]] || { echo "$name is already loaded; keep the current setup." >&2; exit 1; }
    [[ $(modinfo -F vermagic "$base/$name.ko") == "$(uname -r) "* ]] || {
        echo "Kernel version mismatch: $name" >&2; exit 1;
    }
done
loaded=()
cleanup() {
    local index
    for ((index=${#loaded[@]}-1; index>=0; index--)); do rmmod "${loaded[index]}" || true; done
}
trap cleanup EXIT
modprobe qcom_camss
for name in imx615 negroni_extra_sensors negroni_camera_overlay; do
    IFS=, read -r -a dependencies <<< "$(modinfo -F depends "$base/$name.ko")"
    for dependency in "${dependencies[@]}"; do
        case ${dependency//-/_} in
            ''|imx615|negroni_extra_sensors|negroni_camera_overlay) continue;;
        esac
        modprobe "$dependency"
    done
done
insmod "$base/imx615.ko"; loaded+=(imx615)
insmod "$base/negroni_extra_sensors.ko"; loaded+=(negroni_extra_sensors)
insmod "$base/negroni_camera_overlay.ko" firmware=negroni/negroni-four-camera-test.dtbo
loaded+=(negroni_camera_overlay)
trap - EXIT
echo 'Three experimental cameras loaded. AF/OIS and application switching remain incomplete.'
