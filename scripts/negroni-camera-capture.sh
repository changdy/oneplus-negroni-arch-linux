#!/bin/bash
# Experimental S5KJN1 RAW capture on the tested Negroni media graph.
set -euo pipefail

usage() {
    echo "Usage: $0 OUTPUT.raw [FRAMES [TEST_PATTERN [EXPOSURE [GAIN]]]]"
    echo "Use /dev/null to discard frames; defaults: 1 frame, pattern 0, exposure 3840, gain 8."
}

if [[ ${1:-} == --help ]]; then usage; exit 0; fi
[[ $# -ge 1 && $# -le 5 ]] || { usage; exit 2; }
output=$1
frames=${2:-1}
pattern=${3:-0}
exposure=${4:-3840}
gain=${5:-8}
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 2; }
echo 'Experimental: repeated camera starts have caused hard resets; see docs/camera.md.' >&2
for value in "$frames" "$pattern" "$exposure" "$gain"; do
    [[ $value =~ ^[0-9]{1,6}$ ]] || { echo 'Controls must be decimal integers.' >&2; exit 2; }
done
frames=$((10#$frames)); pattern=$((10#$pattern))
exposure=$((10#$exposure)); gain=$((10#$gain))
(( frames >= 1 && frames <= 1800 && pattern <= 4 &&
   exposure >= 8 && exposure <= 4266 && gain >= 1 && gain <= 64 )) || {
    echo 'Invalid frame count or control range.' >&2; exit 2;
}
for command in media-ctl v4l2-ctl timeout flock fuser stat; do
    command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 2; }
done
if [[ $output != /dev/null && ( -e $output || -L $output ) ]]; then
    echo "Output already exists: $output" >&2
    exit 2
fi

exec 9>/run/lock/negroni-camera-capture.lock
flock -n 9 || { echo 'Another capture is running.' >&2; exit 1; }
media=/dev/media0
cci=/sys/devices/platform/soc@0/ac15000.cci/power/control
[[ -c $media && -w $cci ]] || { echo 'CAMSS or CCI is unavailable.' >&2; exit 1; }
sensor=$(media-ctl -d "$media" -e 's5kjn1 6-0010')
video=$(media-ctl -d "$media" -e msm_vfe3_video0)
# WirePlumber keeps the camera nodes open while the desktop is up. That is
# not a capture. Refuse only another process, or a PipeWire stream that is
# actually active.
pids=$(fuser "$media" /dev/video* /dev/v4l-subdev* 2>/dev/null | grep -oE '[0-9]+' | sort -u | tr '\n' ' ' || true)
if [[ -n ${pids// } ]]; then
    names=$(ps -o comm= -p $pids | awk '{$1=$1} NF' | sort -u)
    if [[ $names != wireplumber ]]; then
        echo "Camera is in use: ${names//$'\n'/ }" >&2
        exit 1
    fi
    # This script runs as root. The desktop PipeWire socket belongs to the
    # logged-in user, so a direct wpctl cannot see an active preview.
    desktop_user=oneplus
    runtime=/run/user/$(id -u "$desktop_user")
    if [[ ! -S $runtime/pipewire-0 ]]; then
        echo 'WirePlumber holds the camera, but its PipeWire session is not visible.' >&2
        exit 1
    fi
    status=$(runuser -u "$desktop_user" -- env XDG_RUNTIME_DIR="$runtime" wpctl status) || {
        echo 'WirePlumber holds the camera, but its session cannot be queried.' >&2
        exit 1
    }
    if printf '%s\n' "$status" | sed -n '/^Video$/,/^Settings$/p' | grep -q '\[active\]'; then
        echo 'A camera preview is active; close it before capturing.' >&2
        exit 1
    fi
fi

old_cci=$(cat "$cci")
light=${NEGRONI_CAMERA_LIGHT:-off}
case $light in
    off|torch|flash) ;;
    *) echo 'NEGRONI_CAMERA_LIGHT must be off, torch, or flash.' >&2; exit 2;;
esac
led=/sys/class/leds/white:flash
light_changed=0
old_brightness=0
old_timeout=0
old_flash=0
restore_light() {
    if (( light_changed )); then
        printf '0\n' > "$led/brightness" || true
        printf '%s\n' "$old_timeout" > "$led/flash_timeout" || true
        printf '%s\n' "$old_flash" > "$led/flash_brightness" || true
        printf '%s\n' "$old_brightness" > "$led/brightness" || true
    fi
}
trap 'printf "%s\n" "$old_cci" > "$cci"; restore_light' EXIT
# Keep the I2C controller available while sensor controls are programmed.
echo on > "$cci"
media-ctl -d "$media" -r
media-ctl -d "$media" -l '"msm_csiphy2":1->"msm_csid3":0[1]'
media-ctl -d "$media" -l '"msm_csid3":1->"msm_vfe3_rdi0":0[1]'
v4l2-ctl -d "$sensor" --set-ctrl=horizontal_flip=0,vertical_flip=0
for entity in 's5kjn1 6-0010' msm_csiphy2 msm_csid3 msm_vfe3_rdi0; do
    media-ctl -d "$media" -V "\"$entity\":0[fmt:SGRBG10_1X10/4080x3072]"
done
v4l2-ctl -d "$sensor" \
    --set-ctrl="vertical_blanking=1216,test_pattern=$pattern,exposure=$exposure,analogue_gain=$gain"
v4l2-ctl -d "$video" \
    --set-fmt-video=width=4080,height=3072,pixelformat=pgAA --get-fmt-video

# Include time for four initial frames and sensor startup, then bound a stall.
seconds=$((frames / 30 + 10))
if [[ $light != off ]]; then
    [[ -w $led/brightness && -w $led/flash_brightness && -w $led/flash_strobe ]] || {
        echo 'PMIC flash LED is not writable.' >&2; exit 1;
    }
    old_brightness=$(cat "$led/brightness")
    old_timeout=$(cat "$led/flash_timeout")
    old_flash=$(cat "$led/flash_brightness")
    light_changed=1
    printf '0\n' > "$led/brightness"
    if [[ $light == torch ]]; then
        # About 48/255 of the torch current, held for this capture only.
        printf '48\n' > "$led/brightness"
    else
        max_ua=$(cat "$led/max_flash_brightness")
        max_us=$(cat "$led/max_flash_timeout")
        ua=400000
        us=1200000
        (( ua > max_ua )) && ua=$((max_ua / 2))
        (( us > max_us )) && us=$max_us
        (( ua >= 50000 && us >= 50000 )) || {
            echo 'Flash limits are too small.' >&2; exit 1;
        }
        # Software strobe around STREAMON. It is not synced to a sensor strobe pin.
        printf '%s\n' "$ua" > "$led/flash_brightness"
        printf '%s\n' "$us" > "$led/flash_timeout"
        printf '1\n' > "$led/flash_strobe"
    fi
fi
timeout --signal=INT --kill-after=3 "$seconds" \
    v4l2-ctl -d "$video" --stream-mmap=4 --stream-skip=4 \
    --stream-count="$frames" --stream-to="$output" --verbose
if [[ $output != /dev/null ]]; then
    bytes=$(stat -c %s -- "$output")
    (( bytes == frames * 15679488 )) || { echo "Unexpected capture size: $bytes" >&2; exit 1; }
fi
echo "Captured $frames frame(s): 4080x3072 GRBG RAW10, stride 5104, $output"
