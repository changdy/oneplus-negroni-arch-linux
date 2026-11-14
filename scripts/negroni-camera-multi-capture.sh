#!/bin/bash
# Experimental four-camera RAW capture; modules/overlay must already be loaded.
set -euo pipefail

usage() { echo "Usage: $0 {main|ultrawide|tele|front} OUTPUT.raw [FRAMES [PATTERN]]"; }
if [[ ${1:-} == --help ]]; then usage; exit 0; fi
[[ $# -ge 2 && $# -le 4 && $EUID -eq 0 ]] || { usage >&2; exit 2; }
camera=$1; output=$2; frames=${3:-1}; pattern=${4:-0}
[[ $frames =~ ^[0-9]{1,4}$ && $pattern =~ ^[0-2]$ ]] || exit 2
frames=$((10#$frames)); pattern=$((10#$pattern))
(( frames >= 1 && frames <= 1800 )) || exit 2
[[ $output == /dev/null || ! -e $output && ! -L $output ]] || {
    echo 'Output already exists.' >&2; exit 2;
}
for command in media-ctl v4l2-ctl timeout flock fuser stat; do
    command -v "$command" >/dev/null || { echo "Missing $command" >&2; exit 2; }
done
echo 'Experimental RAW path: camera switching has caused hard resets; see docs/camera.md.' >&2
exec 9>/run/lock/negroni-camera-capture.lock
flock -n 9 || { echo 'Another capture is running.' >&2; exit 1; }
source "$(dirname "$0")/negroni-camera-idle.sh"
negroni_camera_require_idle
case $camera in
    main) entity=imx789; phy=1; csid=1; width=4000; height=3008; stride=5008
          code=SBGGR10_1X10; pixel=pBAA; cci=ac15000.cci;;
    ultrawide) entity='s5kjn1 6-0010'; phy=2; csid=3; width=4080; height=3072; stride=5104
               code=SGRBG10_1X10; pixel=pgAA; cci=ac15000.cci;;
    tele) entity=ov08a10; phy=0; csid=3; width=3264; height=1836; stride=4080
          code=SBGGR10_1X10; pixel=pBAA; cci=ac16000.cci
          (( pattern == 0 )) || { echo 'Tele test pattern is unverified.' >&2; exit 2; };;
    front) entity='imx615 8-0010'; phy=5; csid=4; width=3280; height=2464; stride=4112
           code=SRGGB10_1X10; pixel=pRAA; cci=ac16000.cci;;
    *) usage >&2; exit 2;;
esac
sensor=$(media-ctl -d /dev/media0 -e "$entity")
video=$(media-ctl -d /dev/media0 -e "msm_vfe${csid}_video0")
power=/sys/bus/platform/devices/$cci/power/control
old_power=$(cat "$power")
pattern_file=/sys/module/negroni_extra_sensors/parameters/test_pattern
old_pattern=
cleanup() {
    echo "$old_power" > "$power"
    [[ -z $old_pattern ]] || echo "$old_pattern" > "$pattern_file"
}
trap cleanup EXIT
echo on > "$power"
if [[ $camera == main ]]; then
    old_pattern=$(cat "$pattern_file")
    if (( pattern )); then echo 1 > "$pattern_file"; else echo 0 > "$pattern_file"; fi
elif [[ $camera == front ]]; then
    v4l2-ctl -d "$sensor" --set-ctrl="test_pattern=$pattern"
elif [[ $camera == ultrawide ]]; then
    v4l2-ctl -d "$sensor" --set-ctrl=horizontal_flip=0,vertical_flip=0
fi
media-ctl -d /dev/media0 -r
media-ctl -d /dev/media0 -l "\"msm_csiphy$phy\":1->\"msm_csid$csid\":0[1]"
media-ctl -d /dev/media0 -l "\"msm_csid$csid\":1->\"msm_vfe${csid}_rdi0\":0[1]"
for entity_name in "$entity" "msm_csiphy$phy" "msm_csid$csid" "msm_vfe${csid}_rdi0"; do
    media-ctl -d /dev/media0 -V "\"$entity_name\":0[fmt:$code/${width}x${height}]"
done
if [[ $camera == ultrawide ]]; then
    v4l2-ctl -d "$sensor" --set-ctrl="vertical_blanking=1216,test_pattern=$pattern,exposure=3840,analogue_gain=8"
fi
v4l2-ctl -d "$video" --set-fmt-video="width=$width,height=$height,pixelformat=$pixel" --get-fmt-video
timeout --signal=INT --kill-after=3 "$((frames / 15 + 15))" \
    v4l2-ctl -d "$video" --stream-mmap=4 --stream-skip=4 --stream-count="$frames" \
    --stream-to="$output" --verbose
if [[ $output != /dev/null ]]; then
    bytes=$(stat -c %s -- "$output")
    (( bytes == stride * height * frames )) || { echo "Unexpected RAW size: $bytes" >&2; exit 1; }
fi
echo "Captured $camera: ${width}x${height}, stride $stride, $frames frame(s)"
