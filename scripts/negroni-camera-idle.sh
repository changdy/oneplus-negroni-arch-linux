#!/usr/bin/env bash
# Shared guard: WirePlumber's idle discovery handles are not an active capture.
negroni_camera_require_idle() {
    local pids names desktop_user runtime status
    pids=$(fuser /dev/media0 /dev/video* /dev/v4l-subdev* 2>/dev/null | grep -oE '[0-9]+' | sort -u | tr '\n' ' ' || true)
    [[ -n ${pids// } ]] || return 0
    names=$(ps -o comm= -p $pids | awk '{$1=$1} NF' | sort -u)
    [[ $names == wireplumber ]] || { echo "Camera/video devices are in use: $names" >&2; return 1; }
    desktop_user=${NEGRONI_DESKTOP_USER:-oneplus}
    runtime=/run/user/$(id -u "$desktop_user")
    [[ -S $runtime/pipewire-0 ]] || { echo 'Cannot query the desktop camera session.' >&2; return 1; }
    status=$(runuser -u "$desktop_user" -- env XDG_RUNTIME_DIR="$runtime" LC_ALL=C wpctl status) || return 1
    if printf '%s\n' "$status" | sed -n '/^Video$/,/^Settings$/p' | grep -q '\[active\]'; then
        echo 'A camera preview is active; close it before capturing or changing modules.' >&2
        return 1
    fi
}
