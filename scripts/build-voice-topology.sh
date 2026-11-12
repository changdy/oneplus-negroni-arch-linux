#!/usr/bin/env bash
# Experimental NE2210 AudioReach voice topology; contains owner-supplied ACDB data.
# Usage: build-voice-topology.sh AUDIOREACH_CHECKOUT RX_DIR TX_DIR OUTPUT_BIN [--loopback]
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
src=$(realpath -e -- "${1:?AudioReach checkout required}")
rx=$(realpath -e -- "${2:?Extracted handset RX graph directory required}")
tx=$(realpath -e -- "${3:?Extracted handset TX graph directory required}")
out=$(realpath -m -- "${4:?Output file required (keep outside Git)}")
shift 4
test -f "$src/audioreach/audioreach.m4"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
m4 -I "$src" "$project_dir/config/audio/topology/SM8450-OnePlus-10-Pro.m4" > "$work/base.conf"
python3 - "$work/base.conf" <<'PY'
from pathlib import Path
import re
import sys
p = Path(sys.argv[1])
s = p.read_text()
pattern = r'(SectionWidget\."TERTIARY_MI2S_RX Audio Mixer" \{.*?\n)(\})'
matches = list(re.finditer(pattern, s, re.S))
if len(matches) != 1:
    raise SystemExit("expected exactly one MI2S speaker mixer")
m = matches[0]
body, count = re.subn(r'(^[ \t]*MultiMedia2[ \t]*$)', r'\1\n\t\tMultiMedia5', m[1], flags=re.M)
if count != 1:
    raise SystemExit("expected exactly one MM2 control in the speaker mixer")
s = s[:m.start()] + body + m[2] + s[m.end():]
# The renderer and I2S sink share CID 0x4006. Both graph definitions must
# use GC/global-device/8192, not the base macro's legacy EP/stream values.
matched = 0
def normalize(match):
    global matched
    text = match[0]
    iid = re.search(r'AR_TKN_U32_CONAINER_INSTANCE_ID\s+"([^\"]+)"', text)
    if not iid or int(iid[1], 0) != 0x4006:
        return text
    matched += 1
    for key, value in (("CAPABILITY_ID", "0x0b001001"), ("STACK_SIZE", "8192"),
                       ("GRAPH_POS", "4"), ("PROC_DOMAIN", "2")):
        text, count = re.subn(r'(AR_TKN_U32_CONAINER_' + key + r'\s+)"[^\"]+"',
                             lambda m: m[1] + '"' + value + '"', text)
        if count != 1:
            raise SystemExit("missing shared container property: " + key)
    return text
s = re.sub(r'^SectionVendorTuples\.[^\n]+\{\n.*?^}', normalize, s, flags=re.M | re.S)
if matched != 1:
    raise SystemExit("expected exactly one I2S container")
p.write_text(s)
PY
python3 -I "$project_dir/config/audio/voice/voice-topology.py" "$@" "$rx" "$tx" > "$work/voice.conf"
cat "$work/base.conf" "$work/voice.conf" > "$work/full.conf"
alsatplg -c "$work/full.conf" -o "$work/voice.bin"
test -s "$work/voice.bin"
mkdir -p "$(dirname "$out")"
cp "$work/voice.bin" "$out"
sha256sum "$out"
