#!/usr/bin/env bash
# Install the verified ultrawide userspace and the opt-in four-camera experiment.
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
target_dir=$(realpath -e -- "${1:?Usage: configure-camera.sh ROOTFS LOGS}")
log_dir=$(realpath -m -- "${2:?Usage: configure-camera.sh ROOTFS LOGS}")
[[ $EUID == 0 && $target_dir != / ]] || exit 1
mkdir -p "$log_dir"
if [[ -f "$log_dir/images.complete" ]]; then
    mv "$log_dir/images.complete" "$log_dir/images.complete.before-camera"
fi
rm -f "$log_dir/camera-sources.sha256" "$log_dir/camera-verification.json"
bash "$project_dir/scripts/build-extra-camera-modules.sh" "$target_dir"
cd "$project_dir"
kernel_dir=${KERNEL_DIR:-$project_dir/linux}
sha256sum artifacts/camera-20261114/drivers/*.[ch] \
    artifacts/camera-20261114/drivers/Makefile artifacts/camera-20261114/negroni-four-camera-test.dts \
    config/camera/* scripts/negroni-camera-* scripts/build-extra-camera-modules.sh \
    scripts/configure-camera.sh scripts/camera_manifest.py scripts/verify-camera-image.py \
    scripts/image_feature.py scripts/update-feature-image.sh \
    "$kernel_dir/output/Module.symvers" "$kernel_dir/output/include/config/kernel.release" \
    > "$log_dir/camera-sources.sha256"
chown "${SUDO_UID:-1000}:${SUDO_GID:-1000}" "$log_dir/camera-sources.sha256"
