#!/bin/bash
# One ultrawide still: software exposure, gray-world balance, JPEG, optional flash.
set -euo pipefail

usage() {
    echo "Usage: $0 OUTPUT.jpg [--torch|--flash] [--exposure N] [--gain N] [--no-ae] [--eeprom FILE.bin]"
    echo "Ultrawide only. JPEG is software 2x2 binning, not the Android ISP."
}

here=$(cd "$(dirname "$0")" && pwd)
capture=$here/negroni-camera-capture.sh
meter=$here/negroni-camera-meter.py
output=
light=off
exposure=3840
gain=8
no_ae=0
eeprom=

while [[ $# -gt 0 ]]; do
    case $1 in
        --help) usage; exit 0;;
        --torch)
            [[ $light == off ]] || { echo 'Choose only one of --torch or --flash.' >&2; exit 2; }
            light=torch; shift;;
        --flash)
            [[ $light == off ]] || { echo 'Choose only one of --torch or --flash.' >&2; exit 2; }
            light=flash; shift;;
        --no-ae) no_ae=1; shift;;
        --exposure)
            [[ $# -ge 2 && $2 =~ ^[0-9]+$ ]] || { usage >&2; exit 2; }
            exposure=$((10#$2)); shift 2;;
        --gain)
            [[ $# -ge 2 && $2 =~ ^[0-9]+$ ]] || { usage >&2; exit 2; }
            gain=$((10#$2)); shift 2;;
        --eeprom)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            eeprom=$2; shift 2;;
        --*) usage >&2; exit 2;;
        *)
            [[ -z $output ]] || { usage >&2; exit 2; }
            output=$1; shift;;
    esac
done
[[ -n $output && $output == *.jpg ]] || { usage >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 2; }
(( exposure >= 8 && exposure <= 4266 && gain >= 1 && gain <= 64 )) || {
    echo 'Exposure or gain is outside the ultrawide range.' >&2; exit 2;
}
[[ ! -e $output && ! -L $output && ! -e ${output}.json ]] || {
    echo "Output already exists: $output" >&2; exit 2;
}
for command in python3 ffmpeg bash stat mktemp; do
    command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 2; }
done
[[ -f $capture && -f $meter ]] || { echo 'Capture scripts must sit next to this file.' >&2; exit 2; }

workdir=$(mktemp -d)
cleanup() { rm -rf "$workdir"; }
trap cleanup EXIT

if [[ -n $eeprom ]]; then
    bash "$here/negroni-camera-eeprom.sh" "$eeprom"
fi

env -u NEGRONI_CAMERA_LIGHT bash "$capture" "$workdir/meter.raw" 1 0 "$exposure" "$gain"
python3 "$meter" "$workdir/meter.raw" --camera ultrawide \
    --exposure "$exposure" --gain "$gain" > "$workdir/meter.json"
frame_exposure=$exposure
frame_gain=$gain
if (( ! no_ae )); then
    exposure=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["exposure"])' "$workdir/meter.json")
    gain=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["gain"])' "$workdir/meter.json")
    recapture=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["recapture"])' "$workdir/meter.json")
else
    recapture=False
fi
final=$workdir/meter.raw
if [[ $recapture == True || $light != off ]]; then
    # Light is armed inside the capture, immediately before STREAMON.
    NEGRONI_CAMERA_LIGHT=$light bash "$capture" "$workdir/final.raw" 1 0 "$exposure" "$gain"
    final=$workdir/final.raw
    frame_exposure=$exposure
    frame_gain=$gain
fi
python3 "$meter" "$final" --camera ultrawide \
    --exposure "$frame_exposure" --gain "$frame_gain" --ppm "$workdir/frame.ppm" > "$workdir/final.json"
if ! ffmpeg -hide_banner -loglevel error -i "$workdir/frame.ppm" -q:v 3 "$output"; then
    rm -f -- "$output"
    exit 1
fi
cp "$workdir/final.json" "${output}.json"
echo "Wrote $output from ultrawide exposure=$frame_exposure gain=$frame_gain light=$light"
