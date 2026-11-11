#!/usr/bin/env bash
# Compile the Negroni AudioReach topology with the linux-msm/audioreach-topology macros.
# Usage: build-audio-topology.sh AUDIOREACH_TOPOLOGY_CHECKOUT OUTPUT_DIRECTORY
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
src=$(realpath -e -- "${1:?Usage: build-audio-topology.sh AUDIOREACH_TOPOLOGY_CHECKOUT OUTPUT_DIRECTORY}")
out=$(realpath -m -- "${2:?Usage: build-audio-topology.sh AUDIOREACH_TOPOLOGY_CHECKOUT OUTPUT_DIRECTORY}")
test -f "$src/audioreach/audioreach.m4"
command -v m4 >/dev/null
command -v alsatplg >/dev/null
mkdir -p "$out"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -r "$src/audioreach" "$src/util" "$work/"
cp "$project_dir/config/audio/topology/SM8450-OnePlus-10-Pro.m4" "$work/"
(cd "$work" && m4 -I . SM8450-OnePlus-10-Pro.m4 > OnePlus-10-Pro.conf)
alsatplg -c "$work/OnePlus-10-Pro.conf" -o "$out/OnePlus-10-Pro-tplg.bin"
echo "audioreach-topology $(git -C "$src" rev-parse HEAD 2>/dev/null || echo unknown)" > "$out/OnePlus-10-Pro-tplg.source"
sha256sum "$out/OnePlus-10-Pro-tplg.bin"
