#!/usr/bin/env bash
# Install the SN100 clock fallback. The driver is built by the kernel config.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-nfc.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
log_dir=$(realpath -m -- "${2:?Usage: configure-nfc.sh ROOTFS_DIRECTORY LOG_DIRECTORY}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-nfc"
fi
rm -f "$log_dir/nfc-sources.sha256" "$log_dir/nfc-verification.json"
install -d -o 0 -g 0 -m 0755 "$target_dir/etc/modprobe.d"
install -o 0 -g 0 -m 0644 "$project_dir/config/nfc/nxp-nci.conf" \
    "$target_dir/etc/modprobe.d/nxp-nci.conf"
install -d -o 0 -g 0 -m 0755 "$target_dir/usr/local/sbin"
work=$(mktemp -d /tmp/negroni-nfc-tools.XXXXXX)
trap 'rm -rf "$work"' EXIT
compiler=${CC:-aarch64-linux-gnu-gcc}
for tool in nfc-up nfc-live nfc-sniff nfc-emulate; do
    "$compiler" -O2 -Wall -Wextra "$project_dir/artifacts/nfc-20261114/$tool.c" -o "$work/$tool"
    install -o 0 -g 0 -m 0755 "$work/$tool" "$target_dir/usr/local/sbin/$tool"
done
install -d -o 0 -g 0 -m 0755 "$target_dir/usr/share/negroni/nfc"
python3 - "$target_dir" "$project_dir" <<'PY'
import hashlib, json, sys
from pathlib import Path
root, project = map(Path, sys.argv[1:])
names = ("nfc-up", "nfc-live", "nfc-sniff", "nfc-emulate")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = {
    "sources": {name: digest(project / f"artifacts/nfc-20261114/{name}.c") for name in names},
    "tools": {name: digest(root / f"usr/local/sbin/{name}") for name in names},
}
(root / "usr/share/negroni/nfc/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
cd "$project_dir"
sha256sum config/nfc/nxp-nci.conf artifacts/nfc-20261114/nfc-{up,live,sniff,emulate}.c \
    scripts/configure-nfc.sh scripts/verify-nfc-image.py scripts/image_feature.py \
    scripts/update-feature-image.sh > "$log_dir/nfc-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/nfc-sources.sha256"
